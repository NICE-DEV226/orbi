"""
Orbi Dev — Services du domaine (ORBI-DEV-02).

Règles :
- chaque fonction exige `owner_id` et ne renvoie jamais la ressource d'un autre propriétaire ;
- les transitions d'exécution sont validées puis appliquées de façon atomique (compare-and-set
  sur le statut courant) ; une transition concurrente échoue au lieu d'écraser l'autre ;
- toute exécution reçoit ses identifiants durables (clé d'idempotence, `client_ref`) à la création,
  avant le moindre appel réseau ;
- aucun secret n'est journalisé ni sérialisé.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from beanie import PydanticObjectId
from pymongo import ReturnDocument

from src.orbi_dev.crypto import encrypt_secret
from src.orbi_dev.inputs import parse_name, valid_branch
from src.orbi_dev.models import (
    AuditRecord,
    EventKind,
    Execution,
    ExecutionEvent,
    Integration,
    IntegrationSecret,
    IntegrationStatus,
    Project,
    Task,
    TaskStatus,
)
from src.orbi_dev.redact import sanitize_text
from src.orbi_dev.state import ExecutionStatus, InvalidTransitionError, ensure_transition, is_terminal

DEFAULT_EXECUTION_TIMEOUT = timedelta(hours=2)

class NotFoundError(Exception):
    """Ressource inexistante ou appartenant à un autre propriétaire (indistinguables volontairement)."""


class ConflictError(Exception):
    """Opération refusée par l'état courant de la ressource."""


def _oid(value: str) -> PydanticObjectId:
    try:
        return PydanticObjectId(value)
    except Exception as e:
        raise NotFoundError("Ressource introuvable") from e


async def record_audit(
    actor_id: int, action: str, resource_type: str, resource_id: str, outcome: str = "success", detail: str = ""
) -> None:
    await AuditRecord(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        detail=sanitize_text(detail),
    ).insert()


# ─────────────────────────────────────
# Projets
# ─────────────────────────────────────

async def create_project(owner_id: int, name: str, repo_url: str, default_branch: str = "") -> Project:
    project = Project(owner_id=owner_id, name=name, repo_url=repo_url, default_branch=default_branch)
    await project.insert()
    await record_audit(owner_id, "project.create", "project", str(project.id))
    return project


async def list_projects(owner_id: int) -> list[Project]:
    return await Project.find(Project.owner_id == owner_id, Project.is_archived == False).sort("-created_at").to_list()  # noqa: E712


async def get_project(owner_id: int, project_id: str) -> Project:
    """Un projet, même retiré : une exécution en cours ou passée doit pouvoir retrouver le sien."""
    project = await Project.find_one(Project.id == _oid(project_id), Project.owner_id == owner_id)
    if project is None:
        raise NotFoundError("Projet introuvable")
    return project


async def get_active_project(owner_id: int, project_id: str) -> Project:
    """Un projet utilisable pour du nouveau travail : un projet retiré est introuvable."""
    project = await get_project(owner_id, project_id)
    if project.is_archived:
        raise NotFoundError("Projet introuvable")
    return project


async def update_project(
    owner_id: int, project_id: str, *, name: str | None = None, default_branch: str | None = None
) -> Project:
    """Renomme un projet et/ou change sa branche de départ (`""` = branche par défaut du dépôt)."""
    project = await get_active_project(owner_id, project_id)
    if name is not None:  # l'affectation ne passe pas par les validateurs du modèle : mêmes règles, appliquées ici
        cleaned = parse_name(name)
        if cleaned is None:
            raise ValueError("nom invalide")
        project.name = cleaned
    if default_branch is not None:
        if default_branch and not valid_branch(default_branch):
            raise ValueError("nom de branche invalide")
        project.default_branch = default_branch
    await project.save()
    await record_audit(owner_id, "project.update", "project", str(project.id))
    return project


async def archive_project(owner_id: int, project_id: str) -> Project:
    """Retire un projet de la liste. Ses tâches et exécutions restent consultables ; les exécutions en cours continuent."""
    project = await get_active_project(owner_id, project_id)
    project.is_archived = True
    await project.save()
    await record_audit(owner_id, "project.archive", "project", str(project.id))
    return project


# ─────────────────────────────────────
# Intégrations
# ─────────────────────────────────────

async def create_integration(
    owner_id: int,
    provider: str,
    secret: str,
    label: str = "",
    capabilities: list[str] | None = None,
    scopes: list[str] | None = None,
) -> Integration:
    """Enregistre une intégration ; le secret est chiffré avant d'atteindre la base."""
    integration = Integration(
        owner_id=owner_id,
        provider=provider,
        label=label,
        capabilities=capabilities or [],
        scopes=scopes or [],
        last_verified_at=datetime.now(UTC),
    )
    ciphertext = encrypt_secret(secret)  # échoue avant toute écriture si le chiffrement n'est pas configuré
    await integration.insert()
    try:
        await IntegrationSecret(
            integration_id=str(integration.id), owner_id=owner_id, ciphertext=ciphertext
        ).insert()
    except Exception:
        await integration.delete()  # jamais d'intégration « active » sans son secret
        raise
    await record_audit(owner_id, "integration.connect", "integration", str(integration.id), detail=provider)
    return integration


async def list_integrations(owner_id: int) -> list[Integration]:
    return await Integration.find(Integration.owner_id == owner_id).sort("-connected_at").to_list()


async def get_integration(owner_id: int, integration_id: str) -> Integration:
    integration = await Integration.find_one(Integration.id == _oid(integration_id), Integration.owner_id == owner_id)
    if integration is None:
        raise NotFoundError("Intégration introuvable")
    return integration


async def get_secret_ciphertext(owner_id: int, integration_id: str) -> str | None:
    """Texte chiffré de la clé (usage interne de l'orchestrateur ; jamais renvoyé à l'interface)."""
    secret = await IntegrationSecret.find_one(
        IntegrationSecret.integration_id == integration_id, IntegrationSecret.owner_id == owner_id
    )
    return secret.ciphertext if secret else None


async def mark_integration_invalid(integration: Integration) -> None:
    integration.status = IntegrationStatus.INVALID
    await integration.save()
    await record_audit(integration.owner_id, "integration.invalid", "integration", str(integration.id), "failure")


async def revoke_integration(owner_id: int, integration_id: str) -> Integration:
    """Révocation locale : le secret est effacé. La révocation côté fournisseur relève du connecteur."""
    integration = await get_integration(owner_id, integration_id)
    integration.status = IntegrationStatus.REVOKED
    await IntegrationSecret.find(IntegrationSecret.integration_id == str(integration.id)).delete()
    # Efface aussi un éventuel champ hérité (avant migration) resté dans le document.
    await Integration.get_pymongo_collection().update_one({"_id": integration.id}, {"$unset": {"secret_ciphertext": ""}})
    integration.revoked_at = datetime.now(UTC)
    await integration.save()
    await record_audit(owner_id, "integration.revoke", "integration", str(integration.id))
    return integration


# ─────────────────────────────────────
# Tâches
# ─────────────────────────────────────

async def create_task(owner_id: int, project_id: str, integration_id: str, prompt: str) -> Task:
    project = await get_active_project(owner_id, project_id)
    integration = await get_integration(owner_id, integration_id)
    if integration.status != IntegrationStatus.ACTIVE:
        raise ConflictError("Intégration inactive")
    task = Task(owner_id=owner_id, project_id=str(project.id), integration_id=str(integration.id), prompt=prompt)
    await task.insert()
    await record_audit(owner_id, "task.create", "task", str(task.id))
    return task


async def list_tasks(owner_id: int, limit: int = 50) -> list[Task]:
    return await Task.find(Task.owner_id == owner_id).sort("-created_at").limit(limit).to_list()


async def get_task(owner_id: int, task_id: str) -> Task:
    task = await Task.find_one(Task.id == _oid(task_id), Task.owner_id == owner_id)
    if task is None:
        raise NotFoundError("Tâche introuvable")
    return task


# ─────────────────────────────────────
# Exécutions
# ─────────────────────────────────────

def make_idempotency_key(task_id: str, attempt: int) -> str:
    """Clé stable : la même tentative d'une même tâche donne toujours la même clé."""
    return hashlib.sha256(f"{task_id}:{attempt}".encode()).hexdigest()[:40]


async def create_execution(
    owner_id: int,
    task_id: str,
    *,
    requires_approval: bool = False,
    timeout: timedelta = DEFAULT_EXECUTION_TIMEOUT,
) -> Execution:
    """
    Crée la prochaine tentative d'une tâche (statut `queued` ou `awaiting_approval`).
    Rejette une nouvelle tentative tant qu'une exécution précédente n'est pas terminale.
    """
    task = await get_task(owner_id, task_id)
    integration = await get_integration(owner_id, task.integration_id)
    if integration.status != IntegrationStatus.ACTIVE:
        raise ConflictError("Intégration inactive")

    if (await get_project(owner_id, task.project_id)).is_archived:
        raise ConflictError("Ce projet a été retiré")

    previous = await Execution.find(Execution.task_id == str(task.id), Execution.owner_id == owner_id).to_list()
    if any(not is_terminal(e.status) for e in previous):
        raise ConflictError("Une exécution est déjà en cours pour cette tâche")

    attempt = len(previous) + 1
    execution = Execution(
        owner_id=owner_id,
        task_id=str(task.id),
        integration_id=str(integration.id),
        provider=integration.provider,
        status=ExecutionStatus.AWAITING_APPROVAL if requires_approval else ExecutionStatus.QUEUED,
        attempt=attempt,
        idempotency_key=make_idempotency_key(str(task.id), attempt),
        client_ref=str(uuid.uuid4()),
        deadline_at=datetime.now(UTC) + timeout,
    )
    await execution.insert()
    await _append_event(execution, EventKind.NOTE, message="Tâche enregistrée", to_status=execution.status)
    await record_audit(owner_id, "execution.create", "execution", str(execution.id))
    return execution


async def get_execution(owner_id: int, execution_id: str) -> Execution:
    execution = await Execution.find_one(Execution.id == _oid(execution_id), Execution.owner_id == owner_id)
    if execution is None:
        raise NotFoundError("Exécution introuvable")
    return execution


async def list_executions(owner_id: int, task_id: str | None = None, limit: int = 50) -> list[Execution]:
    conditions: list[Any] = [Execution.owner_id == owner_id]
    if task_id:
        conditions.append(Execution.task_id == task_id)
    return await Execution.find(*conditions).sort("-created_at").limit(limit).to_list()


async def list_active_executions(limit: int = 200) -> list[Execution]:
    """Exécutions à suivre auprès du fournisseur (toutes propriétaires : usage worker uniquement)."""
    active = [ExecutionStatus.RUNNING, ExecutionStatus.CANCEL_REQUESTED, ExecutionStatus.NEEDS_ATTENTION]
    return await Execution.find({"status": {"$in": [s.value for s in active]}}).limit(limit).to_list()


async def list_stuck_queued(older_than: timedelta, limit: int = 100) -> list[Execution]:
    """Exécutions restées `queued` (process arrêté entre la création et le lancement)."""
    cutoff = datetime.now(UTC) - older_than
    return await Execution.find(
        {"status": ExecutionStatus.QUEUED.value, "updated_at": {"$lt": cutoff}}
    ).limit(limit).to_list()


async def list_events(owner_id: int, execution_id: str) -> list[ExecutionEvent]:
    await get_execution(owner_id, execution_id)
    return await ExecutionEvent.find(
        ExecutionEvent.execution_id == execution_id, ExecutionEvent.owner_id == owner_id
    ).sort("seq").to_list()


async def _append_event(
    execution: Execution,
    kind: EventKind,
    *,
    message: str = "",
    from_status: ExecutionStatus | None = None,
    to_status: ExecutionStatus | None = None,
    data: dict[str, Any] | None = None,
) -> ExecutionEvent:
    """Ajoute un événement avec un numéro de séquence attribué atomiquement."""
    updated = await Execution.get_pymongo_collection().find_one_and_update(
        {"_id": execution.id}, {"$inc": {"event_seq": 1}}, return_document=ReturnDocument.AFTER
    )
    event = ExecutionEvent(
        execution_id=str(execution.id),
        owner_id=execution.owner_id,
        seq=updated["event_seq"],
        kind=kind,
        from_status=from_status,
        to_status=to_status,
        message=sanitize_text(message),
        data=data or {},
    )
    await event.insert()
    execution.event_seq = updated["event_seq"]
    return event


_TRANSITION_FIELDS = {
    "external_id", "external_url", "result_summary", "branch", "pr_url",
    "error_category", "error_message", "started_at", "finished_at", "cancel_requested_at",
}


async def transition_execution(
    owner_id: int,
    execution_id: str,
    expected: ExecutionStatus,
    target: ExecutionStatus,
    *,
    message: str = "",
    **fields: Any,
) -> Execution:
    """
    Applique `expected -> target` de façon atomique.

    Lève InvalidTransitionError si la transition est illégale ou si l'état courant n'est plus
    `expected` (changement concurrent) : l'appelant relit l'état et décide.
    """
    unknown = set(fields) - _TRANSITION_FIELDS
    if unknown:
        raise ValueError(f"Champs non autorisés : {sorted(unknown)}")
    ensure_transition(expected, target)

    now = datetime.now(UTC)
    update_fields: dict[str, Any] = {"status": target.value, "updated_at": now}
    for key, value in fields.items():
        update_fields[key] = sanitize_text(value, 2000) if key in {"error_message", "result_summary"} else value
    if is_terminal(target):
        update_fields.setdefault("finished_at", now)

    document = await Execution.get_pymongo_collection().find_one_and_update(
        {"_id": _oid(execution_id), "owner_id": owner_id, "status": expected.value},
        {"$set": update_fields, "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if document is None:
        await get_execution(owner_id, execution_id)  # NotFoundError si inexistante / autre propriétaire
        raise InvalidTransitionError(expected, target)

    execution = await Execution.get(document["_id"])
    await _append_event(
        execution, EventKind.STATUS_CHANGED, message=message, from_status=expected, to_status=target
    )
    await _sync_task_status(execution)
    return execution


async def _sync_task_status(execution: Execution) -> None:
    if execution.status == ExecutionStatus.SUCCEEDED:
        new_status = TaskStatus.COMPLETED
    elif execution.status == ExecutionStatus.CANCELLED:
        new_status = TaskStatus.CANCELLED
    else:
        return
    task = await Task.get(_oid(execution.task_id))
    if task and task.status == TaskStatus.OPEN:
        task.status = new_status
        await task.save()


async def add_event(
    owner_id: int, execution_id: str, kind: EventKind, message: str, data: dict[str, Any] | None = None
) -> ExecutionEvent:
    execution = await get_execution(owner_id, execution_id)
    return await _append_event(execution, kind, message=message, data=data)


async def set_execution_fields(execution: Execution, **fields: Any) -> None:
    """Met à jour des champs de suivi sans changer de statut (ex. identifiant externe, compteurs)."""
    allowed = _TRANSITION_FIELDS | {"poll_count", "last_polled_at", "attempt"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Champs non autorisés : {sorted(unknown)}")
    fields["updated_at"] = datetime.now(UTC)
    await Execution.get_pymongo_collection().update_one({"_id": execution.id}, {"$set": fields})
    for key, value in fields.items():
        setattr(execution, key, value)
