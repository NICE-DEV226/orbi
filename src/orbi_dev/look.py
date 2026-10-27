"""
Orbi Dev — Langage visuel des messages Telegram.

Telegram n'offre que peu de mise en forme ; on s'en tient donc à quelques règles, appliquées partout (accueil, écrans,
cartes de suivi, alertes) pour que le bot ait une seule voix :

- un titre en gras, puis une ligne d'aide en italique ;
- ce que l'utilisateur a écrit (consigne) dans une citation, repliable quand elle est longue ;
- un seul bouton coloré par écran : celui qu'on attend de l'utilisateur (bleu = continuer, vert = lancer, rouge =
  danger). Les retours et les liens restent neutres, sinon plus rien ne se distingue ;
- l'avancement d'une exécution en trois cases (▰▰▱) ;
- aucun emoji : des symboles de texte (○ ◐ ▲ ✓ ✕ pour les états, + ‹ ↻ ↗ pour les actions), identiques partout.

Tout texte venant de l'extérieur doit déjà être échappé (`esc`) avant d'arriver ici.
"""

from telegram import InlineKeyboardButton

from src.orbi_dev.state import ExecutionStatus

# Glyphes d'action (texte, pas d'emoji)
PLUS = "+"
BACK = "‹"
REFRESH = "↻"
EXTERNAL = "↗"

PRIMARY = "primary"
SUCCESS = "success"
DANGER = "danger"

EXPAND_ABOVE = 160  # au-delà, la citation est repliée : l'écran reste lisible


def btn(label: str, data: str, *, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=data, style=style)


def quote(html_text: str, *, expandable: bool | None = None) -> str:
    """Citation Telegram. Repliable d'office si le texte est long."""
    if expandable is None:
        expandable = len(html_text) > EXPAND_ABOVE
    tag = "<blockquote expandable>" if expandable else "<blockquote>"
    return f"{tag}{html_text}</blockquote>"


_STEP = {
    ExecutionStatus.AWAITING_APPROVAL: 0,
    ExecutionStatus.QUEUED: 1,
    ExecutionStatus.RUNNING: 2,
    ExecutionStatus.CANCEL_REQUESTED: 2,
    ExecutionStatus.NEEDS_ATTENTION: 2,
    ExecutionStatus.SUCCEEDED: 3,
}
_STOPPED = (ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT, ExecutionStatus.CANCELLED)


def progress(status: ExecutionStatus) -> str:
    """Trois cases : lancée, en cours, terminée. Une exécution arrêtée garde son avancement et finit par ✕."""
    status = ExecutionStatus(status)
    if status in _STOPPED:
        return "▰▰✕"
    done = _STEP[status]
    return "▰" * done + "▱" * (3 - done)
