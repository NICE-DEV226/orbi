"""
Orbi Dev — Vocabulaire commun au web et à Telegram : libellés d'état, durées écoulées, noms de fournisseurs.

Un seul endroit pour que « En cours », « À vérifier »… s'écrivent pareil dans l'application web, dans les cartes du bot
et dans ses notifications.
"""

from datetime import UTC, datetime

from src.orbi_dev.state import ExecutionStatus

S = ExecutionStatus

# (libellé court, phrase de détail, ton visuel, groupe de la liste)
STATUS_INFO: dict[ExecutionStatus, tuple[str, str, str, str]] = {
    S.QUEUED: ("En attente", "Lancement en cours", "muted", "active"),
    S.RUNNING: ("En cours", "L'agent travaille", "orbit", "active"),
    S.CANCEL_REQUESTED: ("Annulation", "Annulation demandée", "muted", "active"),
    S.AWAITING_APPROVAL: ("Attend votre accord", "En attente de votre accord", "signal", "attention"),
    S.NEEDS_ATTENTION: ("À vérifier", "Une vérification est nécessaire chez le fournisseur", "signal", "attention"),
    S.SUCCEEDED: ("Terminé", "Terminé", "ok", "done"),
    S.FAILED: ("Échec", "L'agent n'a pas abouti", "bad", "done"),
    S.CANCELLED: ("Annulé", "Annulé", "muted", "done"),
    S.TIMED_OUT: ("Trop long", "Arrêté : durée maximale dépassée", "bad", "done"),
}

STATUS_EMOJI: dict[ExecutionStatus, str] = {
    S.QUEUED: "⏳",
    S.RUNNING: "🔄",
    S.CANCEL_REQUESTED: "⏹",
    S.AWAITING_APPROVAL: "✋",
    S.NEEDS_ATTENTION: "⚠️",
    S.SUCCEEDED: "✅",
    S.FAILED: "❌",
    S.CANCELLED: "🚫",
    S.TIMED_OUT: "⏱",
}

PROVIDER_NAMES = {"cursor": "Cursor", "jules": "Jules (Google)", "fake": "Démonstration (factice)"}


def provider_name(value: str) -> str:
    return PROVIDER_NAMES.get(value, value)


def aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def ago(value: datetime | None, now: datetime | None = None) -> str:
    """Durée écoulée en français courant (« il y a 3 min »)."""
    value = aware(value)
    if value is None:
        return ""
    seconds = int(((now or datetime.now(UTC)) - value).total_seconds())
    if seconds < 45:
        return "à l'instant"
    minutes = seconds // 60
    if minutes < 60:
        return f"il y a {max(minutes, 1)} min"
    hours = minutes // 60
    if hours < 24:
        return f"il y a {hours} h"
    days = hours // 24
    if days == 1:
        return "hier"
    if days < 14:
        return f"il y a {days} j"
    return value.strftime("%d/%m/%Y")
