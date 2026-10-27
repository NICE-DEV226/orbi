"""
Orbi Dev — Contrat des connecteurs (spécification §6, ADR-0002).

Le domaine ne connaît que ces types : aucun objet ni code propre à un fournisseur ne le traverse.
Une opération non supportée lève `ConnectorError(UNSUPPORTED_CAPABILITY)`, jamais un faux succès.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class Capability(StrEnum):
    LAUNCH = "launch"
    STATUS = "status"
    CANCEL = "cancel"
    PULL_REQUEST = "pull_request"


class ErrorCategory(StrEnum):
    AUTH_INVALID = "auth_invalid"
    PERMISSION_DENIED = "permission_denied"
    PLAN_OR_QUOTA = "plan_or_quota"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class ConnectorError(Exception):
    """Erreur normalisée. `message` est destiné à l'affichage : il ne contient jamais de secret."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        code: str | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
        outcome_unknown: bool = False,
    ):
        super().__init__(message)
        self.category = category
        self.message = message
        self.code = code  # code fournisseur (ex. agent_id_conflict), utile à l'orchestration
        self.retryable = retryable
        self.retry_after = retry_after
        # True : la requête a pu atteindre le fournisseur (timeout après envoi). Pas de retry aveugle.
        self.outcome_unknown = outcome_unknown


class RemoteStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"  # le fournisseur attend une réponse ou une validation de l'utilisateur chez lui
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True)
class LaunchRequest:
    client_ref: str
    prompt: str
    repo_url: str
    base_branch: str


@dataclass(frozen=True)
class RemoteRun:
    status: RemoteStatus
    external_id: str
    external_url: str | None = None
    summary: str | None = None
    branch: str | None = None
    pr_url: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class VerifyResult:
    capabilities: frozenset[Capability]
    scopes: list[str] = field(default_factory=list)


class BaseConnector:
    """Socle commun : toute opération non implémentée est refusée explicitement."""

    provider: str = ""
    capabilities: frozenset[Capability] = frozenset()

    def external_id_for(self, client_ref: str) -> str | None:
        """Identifiant fournisseur déterministe si le fournisseur accepte un identifiant choisi par le client."""
        return None

    async def find_by_client_ref(self, client_ref: str) -> RemoteRun | None:
        """
        Retrouve une exécution lancée mais dont la réponse a été perdue, quand le fournisseur n'accepte pas
        d'identifiant choisi par le client. None = introuvable (ou non supporté) ; ne crée jamais rien.
        """
        return None

    async def verify(self) -> VerifyResult:
        raise self._unsupported("verify")

    async def launch(self, request: LaunchRequest) -> RemoteRun:
        raise self._unsupported(Capability.LAUNCH)

    async def get(self, external_id: str) -> RemoteRun:
        raise self._unsupported(Capability.STATUS)

    async def cancel(self, external_id: str) -> RemoteRun:
        raise self._unsupported(Capability.CANCEL)

    async def aclose(self) -> None:
        return None

    def _unsupported(self, what: str) -> ConnectorError:
        return ConnectorError(
            ErrorCategory.UNSUPPORTED_CAPABILITY, f"{self.provider} ne supporte pas l'opération « {what} »"
        )


AgentConnectorType = BaseConnector
