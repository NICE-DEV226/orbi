"""
Orbi Dev — Du signal CI GitHub à une tâche en attente d'approbation (ADR-0009).

Un `check_run`, `check_suite` ou `workflow_run` terminé en échec est routé vers chaque projet actif
dont `github_repo` correspond au dépôt de l'événement. Pour chaque projet, une tâche est créée avec
une exécution `awaiting_approval` : rien ne part chez le fournisseur sans validation humaine.

Garanties :
- dédup métier par `Task.source_ref` (`ci:<owner/repo>@<sha>:<check>`) — une tâche ouverte identique
  fait sauter la création, que la redelivery vienne du transport ou d'un second événement ;
- sans intégration active chez le propriétaire, aucune tâche n'est créée (elle serait intestable) ;
- le prompt est un template Orbi : jamais de journal CI brut, seulement le lien vers le contrôle.
"""

import logging
from datetime import UTC, datetime

from pymongo import ReturnDocument
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from src.core.text import esc
from src.models.developer import GithubWebhookLog
from src.orbi_dev import service
from src.orbi_dev.models import (
    EventKind,
    Execution,
    Integration,
    IntegrationStatus,
    Project,
    Task,
    TaskStatus,
)
from src.orbi_dev.state import ExecutionStatus

logger = logging.getLogger("orbi.dev.ci")

CI_EVENTS = ("check_run", "check_suite", "workflow_run")


def source_ref_for(repository: str, sha: str, check_name: str) -> str:
    """Identité métier de la tâche : même dépôt, même commit, même contrôle = même source."""
    return f"ci:{repository}@{sha}:{check_name}"[:500]


def build_ci_prompt(repository: str, check_name: str, sha: str, url: str) -> str:
    """Consigne transmise à l'agent : le contexte utile, sans le journal brut (lien à la place)."""
    lines = [f"Un contrôle CI a échoué sur {repository} (commit {sha}, « {check_name} »)."]
    if url:
        lines.append(f"Journal du contrôle : {url}")
    lines += [
        "",
        "Diagnostique la cause et propose un correctif sur une branche dédiée avec une pull request. "
        "Ne fusionne rien et ne déploie rien.",
    ]
    return "\n".join(lines)


async def _first_active_integration(owner_id: int) -> Integration | None:
    """L'intégration active la plus ancienne du propriétaire (déterministe si plusieurs)."""
    integrations = await Integration.find(
        Integration.owner_id == owner_id, Integration.status == IntegrationStatus.ACTIVE
    ).sort("connected_at").limit(1).to_list()
    return integrations[0] if integrations else None


async def route_ci_event(log: GithubWebhookLog, bot: Bot | None = None) -> int:
    """
    Route un événement CI : échec → tâche `awaiting_approval` par projet concerné ;
    succès → vérification des correctifs dont la PR porte sur la branche testée.
    Retourne le nombre de tâches créées. Idempotent grâce à `source_ref` et `ci_verified_at`.
    """
    if log.event_type not in CI_EVENTS:
        return 0
    details = log.payload_details or {}
    conclusion = details.get("conclusion")
    if conclusion == "success":
        await verify_ci_success(log, details, bot)
        return 0
    if conclusion != "failure":
        return 0

    sha = str(details.get("sha") or "")
    check_name = str(details.get("check_name") or "inconnu")
    url = str(details.get("url") or "")
    ref = source_ref_for(log.repository, sha, check_name)
    prompt = build_ci_prompt(log.repository, check_name, sha, url)

    projects = await Project.find(
        Project.github_repo == log.repository, Project.is_archived == False  # noqa: E712
    ).to_list()

    created = 0
    for project in projects:
        owner_id = project.owner_id
        duplicate = await Task.find(
            Task.owner_id == owner_id, Task.source_ref == ref, Task.status == TaskStatus.OPEN
        ).limit(1).to_list()
        if duplicate:
            continue
        integration = await _first_active_integration(owner_id)
        if integration is None:
            logger.info(
                "Échec CI sur %s : propriétaire %s sans intégration active, aucune tâche créée",
                log.repository, owner_id,
            )
            continue
        try:
            task = await service.create_task(
                owner_id, str(project.id), str(integration.id), prompt, source_ref=ref
            )
            await service.create_execution(owner_id, str(task.id), requires_approval=True)
        except service.ConflictError as e:
            logger.info("Tâche CI non créée pour %s : %s", log.repository, e)
            continue
        created += 1
        logger.info(
            "Échec CI routé : tâche %s en attente d'approbation (propriétaire %s, %s)",
            task.id, owner_id, ref,
        )
    return created


async def verify_ci_success(log: GithubWebhookLog, details: dict, bot: Bot | None) -> int:
    """
    CI verte sur une branche : marque `ci_verified_at` sur les exécutions réussies dont la PR
    porte sur cette branche (une seule fois, prise atomique), journalise et notifie le propriétaire.
    Retourne le nombre d'exécutions vérifiées.
    """
    branch = str(details.get("branch") or "")
    if not branch:
        return 0
    projects = await Project.find(
        Project.github_repo == log.repository, Project.is_archived == False  # noqa: E712
    ).to_list()
    if not projects:
        return 0
    project_ids = {str(p.id) for p in projects}
    tasks = await Task.find({"project_id": {"$in": list(project_ids)}}).to_list()
    if not tasks:
        return 0
    task_ids = {str(t.id) for t in tasks}
    candidates = await Execution.find(
        {
            "task_id": {"$in": list(task_ids)},
            "branch": branch,
            "status": ExecutionStatus.SUCCEEDED.value,
            "pr_url": {"$ne": None},
            "ci_verified_at": None,
        }
    ).to_list()

    verified = 0
    for execution in candidates:
        claimed = await Execution.get_pymongo_collection().find_one_and_update(
            {"_id": execution.id, "ci_verified_at": None},
            {"$set": {"ci_verified_at": datetime.now(UTC), "updated_at": datetime.now(UTC)}},
            return_document=ReturnDocument.AFTER,
        )
        if claimed is None:
            continue  # un autre événement l'a déjà vérifiée
        await service.add_event(
            execution.owner_id, str(execution.id), EventKind.NOTE,
            f"CI verte sur la branche {branch} : correctif vérifié",
        )
        if bot is not None:
            await _notify_verified(bot, execution)
        verified += 1
    return verified


async def _notify_verified(bot: Bot, execution: Execution) -> None:
    """Annonce la vérification au propriétaire ; un échec d'envoi ne remet pas en cause la vérification."""
    try:
        task = await service.get_task(execution.owner_id, execution.task_id)
        project = (await service.get_project(execution.owner_id, task.project_id)).name
    except service.NotFoundError:
        project = "projet supprimé"
    text = (
        f"✅ <b>Correctif vérifié</b>  ·  <b>{esc(project)}</b>\n\n"
        f"La CI est verte sur la branche de la pull request."
    )
    keyboard = None
    pr = execution.pr_url if execution.pr_url and execution.pr_url.startswith("https://") else None
    if pr:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Voir la PR", url=pr)]])
    try:
        await bot.send_message(chat_id=execution.owner_id, text=text, reply_markup=keyboard)
    except TelegramError as e:
        logger.warning("Annonce de vérification CI non remise (%s) : %s", execution.id, e)
