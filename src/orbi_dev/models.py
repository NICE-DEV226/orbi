"""
Orbi Dev — Modèle de domaine minimal du premier parcours (ORBI-DEV-02).

Projet, Intégration, Tâche, Exécution, Événement, Audit. Toute ressource appartient à un
`owner_id` (identité Telegram existante) et n'est jamais lue sans ce filtre côté service.
Aucun secret n'est exposé : le texte chiffré est exclu de la sérialisation et du repr.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from beanie import Document, Indexed
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, IndexModel

from src.orbi_dev.state import ExecutionStatus


def _now() -> datetime:
    return datetime.now(UTC)


class Project(Document):
    owner_id: Indexed(int)  # type: ignore[valid-type]
    name: str = Field(min_length=1, max_length=100)
    repo_url: str
    default_branch: str = Field(default="main", min_length=1, max_length=100)
    is_archived: bool = False
    created_at: datetime = Field(default_factory=_now)

    @field_validator("repo_url")
    @classmethod
    def _https_only(cls, v: str) -> str:
        if not v.startswith("https://") or len(v) > 300 or " " in v:
            raise ValueError("repo_url doit être une URL https")
        return v.rstrip("/")

    class Settings:
        name = "orbi_dev_projects"


class IntegrationStatus(StrEnum):
    ACTIVE = "active"
    INVALID = "invalid"  # jeton refusé par le fournisseur
    REVOKED = "revoked"


class Integration(Document):
    owner_id: Indexed(int)  # type: ignore[valid-type]
    provider: str = Field(min_length=1, max_length=50)
    label: str = Field(default="", max_length=100)
    status: IntegrationStatus = IntegrationStatus.ACTIVE
    capabilities: list[str] = Field(default_factory=list)  # capacités réellement vérifiées
    scopes: list[str] = Field(default_factory=list)  # portées accordées, si le fournisseur les expose
    connected_at: datetime = Field(default_factory=_now)
    last_verified_at: datetime | None = None
    revoked_at: datetime | None = None

    class Settings:
        name = "orbi_dev_integrations"


class IntegrationSecret(Document):
    """
    Texte chiffré de la clé d'une intégration, isolé dans sa propre collection.

    Il ne fait volontairement pas partie du document `Integration` : aucun modèle renvoyé à l'interface ou
    sérialisé ne peut donc le contenir. (Un champ `exclude=True` n'est de toute façon pas persisté par Beanie 2.)
    """

    integration_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    owner_id: Indexed(int)  # type: ignore[valid-type]
    ciphertext: str = Field(repr=False)
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "orbi_dev_integration_secrets"


class TaskStatus(StrEnum):
    OPEN = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Task(Document):
    owner_id: Indexed(int)  # type: ignore[valid-type]
    project_id: str
    integration_id: str
    prompt: str = Field(min_length=1, max_length=8000)
    status: TaskStatus = TaskStatus.OPEN
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "orbi_dev_tasks"


class Execution(Document):
    owner_id: Indexed(int)  # type: ignore[valid-type]
    task_id: Indexed(str)  # type: ignore[valid-type]
    integration_id: str
    provider: str
    status: ExecutionStatus = ExecutionStatus.QUEUED
    attempt: int = 1

    # Identité durable, créée AVANT tout appel réseau (ADR-0003).
    idempotency_key: str
    client_ref: str  # identifiant choisi par Orbi, transmis au fournisseur quand il le permet
    external_id: str | None = None  # identifiant attribué par le fournisseur
    external_url: str | None = None

    # Résultat
    result_summary: str | None = None
    branch: str | None = None
    pr_url: str | None = None
    error_category: str | None = None
    error_message: str | None = None  # déjà filtré, sans secret

    # Suivi
    version: int = 0  # incrémenté à chaque transition (contrôle de concurrence)
    event_seq: int = 0
    poll_count: int = 0
    last_polled_at: datetime | None = None
    deadline_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "orbi_dev_executions"
        indexes = [
            IndexModel([("idempotency_key", ASCENDING)], unique=True),
            IndexModel([("client_ref", ASCENDING)], unique=True),
            IndexModel([("status", ASCENDING), ("updated_at", ASCENDING)]),
        ]


class EventKind(StrEnum):
    STATUS_CHANGED = "status_changed"
    PROGRESS = "progress"
    RECONCILIATION = "reconciliation"
    ERROR = "error"
    NOTE = "note"


class ExecutionEvent(Document):
    """Événement opérationnel, en ajout seul. L'état de vérité reste `Execution.status`."""

    execution_id: str
    owner_id: Indexed(int)  # type: ignore[valid-type]
    seq: int
    kind: EventKind
    from_status: ExecutionStatus | None = None
    to_status: ExecutionStatus | None = None
    message: str = Field(default="", max_length=500)
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "orbi_dev_events"
        indexes = [IndexModel([("execution_id", ASCENDING), ("seq", ASCENDING)], unique=True)]


class AuditRecord(Document):
    """Qui a fait quoi sur quelle ressource (distinct des événements opérationnels)."""

    actor_id: Indexed(int)  # type: ignore[valid-type]
    action: str
    resource_type: str
    resource_id: str
    outcome: str = "success"
    detail: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "orbi_dev_audit"


class ExecutionView(BaseModel):
    """Projection sûre d'une exécution pour l'interface (aucun identifiant de secret)."""

    id: str
    task_id: str
    provider: str
    status: ExecutionStatus
    attempt: int
    external_url: str | None
    result_summary: str | None
    branch: str | None
    pr_url: str | None
    error_category: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
