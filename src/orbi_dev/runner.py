"""
Orbi Dev — Orchestration des exécutions auprès d'un fournisseur (ORBI-DEV-03).

Garanties (ADR-0003) :
- l'identité de l'exécution existe avant l'appel réseau ; un lancement répété est sans effet externe en double ;
- un résultat incertain (délai dépassé après envoi) est réconcilié par lecture, jamais relancé à l'aveugle ;
- les retries sont bornés et limités aux erreurs réessayables ;
- une annulation non supportée est refusée explicitement, jamais simulée ;
- toutes les transitions passent par `service.transition_execution` (atomique, validée).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from src.orbi_dev import service
from src.orbi_dev.connectors.base import (
    AgentConnectorType,
    Capability,
    ConnectorError,
    ErrorCategory,
    LaunchRequest,
    RemoteRun,
    RemoteStatus,
)
from src.orbi_dev.connectors.registry import build_connector
from src.orbi_dev.crypto import SecretDecryptionError, SecretsNotConfiguredError, decrypt_secret
from src.orbi_dev.models import EventKind, Execution, Integration, IntegrationStatus
from src.orbi_dev.state import ExecutionStatus, InvalidTransitionError, can_transition, is_terminal

logger = logging.getLogger("orbi.dev.runner")

MAX_LAUNCH_ATTEMPTS = 3
STUCK_QUEUED_AFTER = timedelta(seconds=60)
LOST_LAUNCH_GRACE = timedelta(minutes=10)

Sleep = Callable[[float], Awaitable[None]]

_REMOTE_TO_STATUS = {
    RemoteStatus.PENDING: ExecutionStatus.RUNNING,
    RemoteStatus.RUNNING: ExecutionStatus.RUNNING,
    RemoteStatus.SUCCEEDED: ExecutionStatus.SUCCEEDED,
    RemoteStatus.FAILED: ExecutionStatus.FAILED,
    RemoteStatus.CANCELLED: ExecutionStatus.CANCELLED,
    RemoteStatus.EXPIRED: ExecutionStatus.TIMED_OUT,
}


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class _Session:
    """Connecteur ouvert pour la durée d'une opération (le secret n'est déchiffré qu'ici)."""

    def __init__(self, integration: Integration):
        self.integration = integration
        self.connector: AgentConnectorType | None = None

    async def __aenter__(self) -> AgentConnectorType:
        ciphertext = None
        if self.integration.status == IntegrationStatus.ACTIVE:
            ciphertext = await service.get_secret_ciphertext(self.integration.owner_id, str(self.integration.id))
        if not ciphertext:
            raise ConnectorError(ErrorCategory.AUTH_INVALID, "Intégration inactive ou révoquée")
        try:
            secret = decrypt_secret(ciphertext)
        except (SecretDecryptionError, SecretsNotConfiguredError) as e:
            raise ConnectorError(ErrorCategory.AUTH_INVALID, "Secret d'intégration illisible") from e
        self.connector = build_connector(self.integration.provider, secret)
        return self.connector

    async def __aexit__(self, *exc: object) -> None:
        if self.connector is not None:
            await self.connector.aclose()


# ─────────────────────────────────────
# Intégration
# ─────────────────────────────────────

async def connect_integration(owner_id: int, provider: str, secret: str, label: str = "") -> Integration:
    """Vérifie la clé auprès du fournisseur AVANT de la stocker."""
    connector = build_connector(provider, secret)
    try:
        result = await connector.verify()
    except ConnectorError as e:
        await service.record_audit(owner_id, "integration.connect", "integration", provider, "failure", e.category.value)
        raise
    finally:
        await connector.aclose()
    return await service.create_integration(
        owner_id, provider, secret, label=label, capabilities=sorted(c.value for c in result.capabilities),
        scopes=result.scopes,
    )


async def revoke_integration(owner_id: int, integration_id: str) -> Integration:
    """
    Révoque localement (secret effacé) et met les exécutions actives en `needs_attention` :
    sans secret, Orbi ne peut plus les suivre. La clé reste valide chez le fournisseur tant que
    l'utilisateur ne la supprime pas dans son tableau de bord (aucune API de révocation exploitée).
    """
    integration = await service.revoke_integration(owner_id, integration_id)
    for execution in await service.list_executions(owner_id, limit=200):
        if execution.integration_id != integration_id or is_terminal(execution.status):
            continue
        if can_transition(execution.status, ExecutionStatus.NEEDS_ATTENTION):
            await _safe_transition(
                execution, ExecutionStatus.NEEDS_ATTENTION,
                message="Intégration révoquée : suivi impossible, vérifiez chez le fournisseur",
                error_category=ErrorCategory.AUTH_INVALID.value,
            )
    return integration


# ─────────────────────────────────────
# Transitions
# ─────────────────────────────────────

async def _safe_transition(execution: Execution, target: ExecutionStatus, *, message: str = "", **fields) -> Execution:
    """Transition tolérant la concurrence : si un autre acteur a déjà avancé l'état, on relit sans écraser."""
    try:
        return await service.transition_execution(
            execution.owner_id, str(execution.id), execution.status, target, message=message, **fields
        )
    except InvalidTransitionError:
        return await service.get_execution(execution.owner_id, str(execution.id))


def _remote_fields(remote: RemoteRun) -> dict:
    fields = {
        "external_id": remote.external_id, "external_url": remote.external_url,
        "branch": remote.branch, "pr_url": remote.pr_url,
    }
    if remote.summary:
        fields["result_summary"] = remote.summary
    return {k: v for k, v in fields.items() if v is not None}


# Phrase d'historique selon l'état atteint, quand l'appelant n'en fournit pas.
_TARGET_MESSAGE = {
    ExecutionStatus.RUNNING: "L'agent travaille",
    ExecutionStatus.SUCCEEDED: "L'agent a terminé",
    ExecutionStatus.FAILED: "L'agent n'a pas abouti",
    ExecutionStatus.CANCELLED: "Exécution annulée",
    ExecutionStatus.TIMED_OUT: "Arrêtée : durée maximale dépassée",
}


async def _converge(execution: Execution, remote: RemoteRun, *, message: str | None = None) -> Execution:
    """Aligne l'exécution sur l'état distant, en passant par `running` si la table l'exige."""
    target = _REMOTE_TO_STATUS[remote.status]
    message = message or _TARGET_MESSAGE[target] + (" : une pull request est prête" if target == ExecutionStatus.SUCCEEDED and remote.pr_url else "")
    fields = _remote_fields(remote)
    if target in (ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT):
        fields["error_message"] = remote.error_message or "Échec signalé par le fournisseur"
        fields["error_category"] = ErrorCategory.UNKNOWN.value

    if execution.status == target:
        if fields:
            await service.set_execution_fields(execution, **{k: v for k, v in fields.items() if k != "error_category"})
        return execution
    if not can_transition(execution.status, target):
        if can_transition(execution.status, ExecutionStatus.RUNNING) and can_transition(ExecutionStatus.RUNNING, target):
            execution = await _safe_transition(execution, ExecutionStatus.RUNNING, message="L'agent a pris la tâche")
        else:
            return execution
    if execution.status == ExecutionStatus.RUNNING and target == ExecutionStatus.RUNNING:
        return execution
    return await _safe_transition(execution, target, message=message, **fields)


# ─────────────────────────────────────
# Lancement
# ─────────────────────────────────────

async def launch_execution(owner_id: int, execution_id: str, *, sleep: Sleep = asyncio.sleep) -> Execution:
    """Lance une exécution `queued`. Peut être rappelée sans danger : le lancement est idempotent."""
    execution = await service.get_execution(owner_id, execution_id)
    if execution.status != ExecutionStatus.QUEUED:
        raise service.ConflictError(f"Lancement impossible depuis l'état {execution.status.value}")

    integration = await service.get_integration(owner_id, execution.integration_id)
    task = await service.get_task(owner_id, execution.task_id)
    project = await service.get_project(owner_id, task.project_id)

    try:
        async with _Session(integration) as connector:
            external_id = connector.external_id_for(execution.client_ref)
            if external_id and not execution.external_id:
                await service.set_execution_fields(execution, external_id=external_id)  # persisté avant l'appel
            request = LaunchRequest(execution.client_ref, task.prompt, project.repo_url, project.default_branch)
            return await _launch_with_retries(execution, connector, request, sleep)
    except ConnectorError as e:
        return await _fail_from_error(execution, e, integration)


async def _launch_with_retries(
    execution: Execution, connector: AgentConnectorType, request: LaunchRequest, sleep: Sleep
) -> Execution:
    last_error: ConnectorError | None = None
    for attempt in range(1, MAX_LAUNCH_ATTEMPTS + 1):
        try:
            remote = await connector.launch(request)
        except ConnectorError as e:
            last_error = e
            if e.outcome_unknown or e.category == ErrorCategory.TIMEOUT:
                return await _reconcile_unknown_launch(execution, connector)
            if e.retryable and attempt < MAX_LAUNCH_ATTEMPTS:
                await sleep(e.retry_after if e.retry_after is not None else min(2**attempt, 8))
                continue
            raise
        return await _converge(execution, remote, message="L'agent a démarré")
    raise last_error or ConnectorError(ErrorCategory.UNKNOWN, "Lancement impossible")


async def _reconcile_unknown_launch(execution: Execution, connector: AgentConnectorType) -> Execution:
    """Réponse perdue : on lit l'état distant. Introuvable ou illisible => `needs_attention`, pas de relance."""
    remote: RemoteRun | None = None
    external_id = execution.external_id
    if external_id:
        try:
            remote = await connector.get(external_id)
        except ConnectorError as e:
            logger.info("Réconciliation du lancement impossible (%s)", e.category)
    if remote is not None:
        await service.add_event(
            execution.owner_id, str(execution.id), EventKind.RECONCILIATION,
            "Réponse de lancement perdue ; exécution retrouvée chez le fournisseur",
        )
        return await _converge(execution, remote, message="Exécution retrouvée chez le fournisseur après une coupure")
    return await _safe_transition(
        execution, ExecutionStatus.NEEDS_ATTENTION,
        message="Résultat du lancement inconnu : vérification en cours, aucun nouveau lancement automatique",
        error_category=ErrorCategory.TIMEOUT.value,
    )


async def _fail_from_error(execution: Execution, error: ConnectorError, integration: Integration) -> Execution:
    if error.category == ErrorCategory.AUTH_INVALID and integration.status == IntegrationStatus.ACTIVE:
        await service.mark_integration_invalid(integration)
    current = await service.get_execution(execution.owner_id, str(execution.id))
    if is_terminal(current.status) or current.status == ExecutionStatus.NEEDS_ATTENTION:
        return current
    return await _safe_transition(
        current, ExecutionStatus.FAILED,
        message=f"Échec : {error.category.value}",
        error_category=error.category.value, error_message=error.message,
    )


# ─────────────────────────────────────
# Suivi
# ─────────────────────────────────────

async def refresh_execution(owner_id: int, execution_id: str) -> Execution:
    """Interroge le fournisseur une fois et fait converger l'état local. Idempotent."""
    execution = await service.get_execution(owner_id, execution_id)
    if is_terminal(execution.status) or execution.status in (ExecutionStatus.AWAITING_APPROVAL,):
        return execution
    if execution.status == ExecutionStatus.QUEUED:
        return execution  # le lancement est traité par launch_execution

    deadline = _aware(execution.deadline_at)
    if deadline and datetime.now(UTC) > deadline:
        return await _time_out(execution)

    integration = await service.get_integration(owner_id, execution.integration_id)
    if not execution.external_id:
        return await _handle_missing_remote(execution)

    try:
        async with _Session(integration) as connector:
            remote = await connector.get(execution.external_id)
    except ConnectorError as e:
        return await _handle_poll_error(execution, e, integration)

    await service.set_execution_fields(
        execution, poll_count=execution.poll_count + 1, last_polled_at=datetime.now(UTC)
    )
    previous = execution.status
    execution = await _converge(execution, remote)
    if previous == ExecutionStatus.NEEDS_ATTENTION and execution.status != previous:
        await service.add_event(
            owner_id, execution_id, EventKind.RECONCILIATION, f"Réconcilié : {execution.status.value}"
        )
    return execution


async def _handle_missing_remote(execution: Execution) -> Execution:
    started = _aware(execution.created_at) or datetime.now(UTC)
    if datetime.now(UTC) - started > LOST_LAUNCH_GRACE:
        return await _safe_transition(
            execution, ExecutionStatus.FAILED,
            message="Aucune trace chez le fournisseur : le lancement n'a pas abouti",
            error_category=ErrorCategory.NOT_FOUND.value, error_message="Exécution introuvable chez le fournisseur",
        )
    return execution


async def _handle_poll_error(execution: Execution, error: ConnectorError, integration: Integration) -> Execution:
    await service.set_execution_fields(execution, poll_count=execution.poll_count + 1, last_polled_at=datetime.now(UTC))
    if error.category == ErrorCategory.AUTH_INVALID:
        if integration.status == IntegrationStatus.ACTIVE:
            await service.mark_integration_invalid(integration)
        return await _to_needs_attention(execution, "Accès refusé par le fournisseur : reconnectez l'intégration", error)
    if error.category == ErrorCategory.NOT_FOUND:
        return await _to_needs_attention(execution, "L'exécution n'existe plus chez le fournisseur", error)
    logger.info("Suivi %s en échec temporaire (%s)", execution.id, error.category)
    return execution  # erreur transitoire : on réessaiera au prochain passage


async def _to_needs_attention(execution: Execution, message: str, error: ConnectorError) -> Execution:
    if execution.status == ExecutionStatus.NEEDS_ATTENTION or not can_transition(
        execution.status, ExecutionStatus.NEEDS_ATTENTION
    ):
        return execution
    return await _safe_transition(
        execution, ExecutionStatus.NEEDS_ATTENTION, message=message,
        error_category=error.category.value, error_message=error.message,
    )


async def _time_out(execution: Execution) -> Execution:
    """Échéance dépassée : annulation au mieux côté fournisseur, puis `timed_out` côté Orbi."""
    if execution.external_id:
        integration = await service.get_integration(execution.owner_id, execution.integration_id)
        try:
            async with _Session(integration) as connector:
                if Capability.CANCEL in connector.capabilities:
                    await connector.cancel(execution.external_id)
        except ConnectorError as e:
            logger.info("Annulation à l'échéance impossible (%s)", e.category)
    return await _safe_transition(
        execution, ExecutionStatus.TIMED_OUT, message="Échéance dépassée",
        error_category=ErrorCategory.TIMEOUT.value, error_message="Durée maximale d'exécution dépassée",
    )


async def refresh_active_executions() -> int:
    """Passage worker : suit les exécutions actives et relance les lancements restés en file. Retourne le nombre traité."""
    processed = 0
    for execution in await service.list_stuck_queued(STUCK_QUEUED_AFTER):
        try:
            await launch_execution(execution.owner_id, str(execution.id))
            processed += 1
        except Exception:
            logger.exception("Relance du lancement %s en échec", execution.id)
    for execution in await service.list_active_executions():
        try:
            await refresh_execution(execution.owner_id, str(execution.id))
            processed += 1
        except Exception:
            logger.exception("Suivi de l'exécution %s en échec", execution.id)
    return processed


# ─────────────────────────────────────
# Annulation
# ─────────────────────────────────────

async def request_cancel(owner_id: int, execution_id: str) -> Execution:
    """
    Demande l'annulation. Avant lancement : annulation locale immédiate. Après lancement : seulement si le
    fournisseur la supporte (sinon erreur de capacité explicite) ; l'état final est confirmé par le fournisseur.
    """
    execution = await service.get_execution(owner_id, execution_id)
    if is_terminal(execution.status):
        raise service.ConflictError("Exécution déjà terminée")
    if execution.status in (ExecutionStatus.AWAITING_APPROVAL, ExecutionStatus.QUEUED) and not execution.external_id:
        return await _safe_transition(execution, ExecutionStatus.CANCELLED, message="Annulée avant lancement")
    if execution.status == ExecutionStatus.CANCEL_REQUESTED:
        return execution

    integration = await service.get_integration(owner_id, execution.integration_id)
    async with _Session(integration) as connector:
        if Capability.CANCEL not in connector.capabilities:
            raise ConnectorError(
                ErrorCategory.UNSUPPORTED_CAPABILITY, f"{integration.provider} ne permet pas d'annuler une exécution"
            )
        if can_transition(execution.status, ExecutionStatus.CANCEL_REQUESTED):
            execution = await _safe_transition(
                execution, ExecutionStatus.CANCEL_REQUESTED, message="Annulation demandée",
                cancel_requested_at=datetime.now(UTC),
            )
        try:
            remote = await connector.cancel(execution.external_id or "")
        except ConnectorError as e:
            if e.category == ErrorCategory.CONFLICT:  # déjà terminée côté fournisseur : on relit
                return await refresh_execution(owner_id, execution_id)
            if e.category == ErrorCategory.NOT_FOUND:  # le lancement n'a jamais abouti : rien à annuler
                return await _safe_transition(execution, ExecutionStatus.CANCELLED, message="Annulée : inconnue du fournisseur")
            raise
    return await _converge(execution, remote, message="Annulation confirmée")
