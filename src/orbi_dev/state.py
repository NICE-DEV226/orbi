"""
Orbi Dev — Machine à états des exécutions (ADR-0003).

Module pur (sans I/O) : les transitions sont validées ici puis appliquées de façon
atomique par le service. Un état terminal n'accepte plus aucune transition ; un résultat
externe incertain passe par `needs_attention` (réconciliation), jamais par un retry aveugle.
"""

from enum import StrEnum


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    NEEDS_ATTENTION = "needs_attention"


S = ExecutionStatus

TERMINAL_STATUSES: frozenset[ExecutionStatus] = frozenset({S.SUCCEEDED, S.FAILED, S.CANCELLED, S.TIMED_OUT})

# États dont l'exécution est encore à suivre auprès du fournisseur.
ACTIVE_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {S.QUEUED, S.RUNNING, S.CANCEL_REQUESTED, S.NEEDS_ATTENTION}
)

ALLOWED_TRANSITIONS: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    S.AWAITING_APPROVAL: frozenset({S.QUEUED, S.CANCELLED}),
    S.QUEUED: frozenset({S.RUNNING, S.FAILED, S.CANCEL_REQUESTED, S.CANCELLED, S.TIMED_OUT, S.NEEDS_ATTENTION}),
    # RUNNING -> CANCELLED : annulation décidée côté fournisseur (hors Orbi).
    S.RUNNING: frozenset({S.SUCCEEDED, S.FAILED, S.CANCEL_REQUESTED, S.CANCELLED, S.TIMED_OUT, S.NEEDS_ATTENTION}),
    # L'annulation peut perdre la course contre la fin naturelle du travail.
    S.CANCEL_REQUESTED: frozenset({S.CANCELLED, S.SUCCEEDED, S.FAILED, S.TIMED_OUT, S.NEEDS_ATTENTION}),
    # Après réconciliation, l'état réel du fournisseur est adopté.
    S.NEEDS_ATTENTION: frozenset({S.RUNNING, S.SUCCEEDED, S.FAILED, S.CANCEL_REQUESTED, S.CANCELLED, S.TIMED_OUT}),
    S.SUCCEEDED: frozenset(),
    S.FAILED: frozenset(),
    S.CANCELLED: frozenset(),
    S.TIMED_OUT: frozenset(),
}


class InvalidTransitionError(Exception):
    """Transition d'état refusée (illégale ou concurrente)."""

    def __init__(self, current: ExecutionStatus, target: ExecutionStatus):
        self.current = current
        self.target = target
        super().__init__(f"Transition interdite : {current.value} -> {target.value}")


def can_transition(current: ExecutionStatus, target: ExecutionStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def ensure_transition(current: ExecutionStatus, target: ExecutionStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)


def is_terminal(status: ExecutionStatus) -> bool:
    return status in TERMINAL_STATUSES
