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

from src.models.developer import GithubWebhookLog
from src.orbi_dev import service
from src.orbi_dev.models import Integration, IntegrationStatus, Project, Task, TaskStatus

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


async def route_ci_event(log: GithubWebhookLog) -> int:
    """
    Pour un événement CI en échec : crée une tâche `awaiting_approval` par projet concerné.
    Retourne le nombre de tâches créées. Idempotent grâce à `source_ref`.
    """
    if log.event_type not in CI_EVENTS:
        return 0
    details = log.payload_details or {}
    if details.get("conclusion") != "failure":
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
