"""
Orbi Dev — Notifications Telegram de fin d'exécution.

Le worker de suivi appelle `notify_pending` après chaque passage : toute exécution arrivée dans un état à signaler
est annoncée **à son propriétaire seul** (`owner_id`, conversation privée avec le bot). Il n'y a aucun effet de bord
dans les transitions : l'état en base reste la vérité, et un redémarrage du bot ne fait rien perdre.

Garanties :
- une seule annonce par état (marqueur `notified_status`, pris de façon atomique avant l'envoi) ;
- un échec passager (réseau, limite de débit) rend le marqueur et réessaie au passage suivant, 5 fois au plus ;
- un utilisateur qui a bloqué le bot, désactivé ces notifications ou perdu l'accès n'est pas relancé ;
- les anciennes exécutions ne sont jamais annoncées (fenêtre de 6 h), ni en rafale au premier déploiement.
"""

import logging
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, ReplyParameters, WebAppInfo
from telegram.error import Forbidden, TelegramError

from src.core.config import get_settings
from src.core.text import esc
from src.models.user import NotificationPreferences, User
from src.orbi_dev import service
from src.orbi_dev.access import can_use_orbi_dev
from src.orbi_dev.look import PRIMARY, quote
from src.orbi_dev.models import Execution
from src.orbi_dev.state import ExecutionStatus

logger = logging.getLogger("orbi.dev.notifier")

S = ExecutionStatus

NOTIFY_STATUSES: frozenset[ExecutionStatus] = frozenset({S.SUCCEEDED, S.FAILED, S.TIMED_OUT, S.NEEDS_ATTENTION})
MAX_AGE = timedelta(hours=6)
MAX_ATTEMPTS = 5
BATCH = 50

# Préfixes des boutons du message (gérés par src/handlers/orbi_dev.py)
CB_RETRY = "devx:retry:"
CB_CHECK = "devx:check:"

_HEADLINES: dict[ExecutionStatus, str] = {
    S.SUCCEEDED: "✅ <b>Terminé</b>",
    S.FAILED: "❌ <b>Échec</b>",
    S.TIMED_OUT: "⏱ <b>Trop long</b>",
    S.NEEDS_ATTENTION: "⚠️ <b>À vérifier</b>",
}
_FALLBACK_DETAIL: dict[ExecutionStatus, str] = {
    S.FAILED: "L'agent n'a pas abouti.",
    S.TIMED_OUT: "Arrêté : durée maximale dépassée.",
    S.NEEDS_ATTENTION: "Une vérification est nécessaire chez le fournisseur.",
}


def first_line(text: str, limit: int) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


def build_text(execution: Execution, prompt: str, project: str) -> str:
    """Message d'annonce (HTML Telegram : tout texte venant de l'extérieur est échappé)."""
    status = ExecutionStatus(execution.status)
    detail = execution.result_summary if status == S.SUCCEEDED else execution.error_message
    detail = first_line(detail or "", 300) or _FALLBACK_DETAIL.get(status, "")
    lines = [f"{_HEADLINES[status]}  ·  <b>{esc(project)}</b>"]
    if prompt:
        lines += ["", quote(esc(first_line(prompt, 120)), expandable=False)]
    if detail:
        lines.append(esc(detail))
    return "\n".join(lines)


def _safe_https(url: str | None) -> str | None:
    return url if url and url.startswith("https://") and " " not in url else None


def build_keyboard(execution: Execution, *, with_action: bool = True) -> InlineKeyboardMarkup | None:
    """Ouvrir (Mini App, seulement si l'URL publique est en https), voir la PR, puis l'action qui convient."""
    settings = get_settings()
    status = ExecutionStatus(execution.status)
    top: list[InlineKeyboardButton] = []
    if settings.public_https:
        url = f"{settings.BASE_URL.rstrip('/')}/dev/executions/{execution.id}"
        top.append(InlineKeyboardButton("📱 Ouvrir", web_app=WebAppInfo(url=url)))
    pr = _safe_https(execution.pr_url)
    if pr:
        top.append(InlineKeyboardButton("🔀 Voir la PR", url=pr))
    provider = _safe_https(execution.external_url)
    if provider and status == S.NEEDS_ATTENTION:
        top.append(InlineKeyboardButton("↗ Ouvrir chez le fournisseur", url=provider))
    rows = [top] if top else []
    if not with_action:
        pass
    elif status in (S.FAILED, S.TIMED_OUT):
        rows.append([InlineKeyboardButton("🔁 Réessayer", callback_data=f"{CB_RETRY}{execution.id}", style=PRIMARY)])
    elif status == S.NEEDS_ATTENTION:
        rows.append([InlineKeyboardButton("🔄 Vérifier maintenant", callback_data=f"{CB_CHECK}{execution.id}")])
    elif status in (S.QUEUED, S.RUNNING, S.CANCEL_REQUESTED):
        rows.append([InlineKeyboardButton("🔄 Actualiser", callback_data=f"{CB_CHECK}{execution.id}")])
    return InlineKeyboardMarkup(rows) if rows else None


async def _claim(execution: Execution) -> Execution | None:
    """Prend l'annonce de cet état (atomique) ; None si un autre passage l'a déjà prise ou si l'état a changé."""
    document = await Execution.get_pymongo_collection().find_one_and_update(
        {"_id": execution.id, "status": execution.status.value, "notified_status": {"$ne": execution.status.value}},
        {"$set": {"notified_status": execution.status.value}},
        return_document=ReturnDocument.AFTER,
    )
    return await Execution.get(document["_id"]) if document else None


async def _release(execution: Execution, previous: str | None) -> None:
    """Échec passager : rend l'annonce au passage suivant et compte l'échec (borné par MAX_ATTEMPTS)."""
    await Execution.get_pymongo_collection().update_one(
        {"_id": execution.id, "notified_status": execution.status.value},
        {"$set": {"notified_status": previous}, "$inc": {"notify_attempts": 1}},
    )


async def _announce(bot: Bot, execution: Execution) -> str:
    """Retourne 'sent', 'skipped' (rien à envoyer) ou 'retry' (échec passager)."""
    owner = await User.find_one(User.telegram_id == execution.owner_id)
    if not can_use_orbi_dev(owner) or NotificationPreferences.DEV_RUNS not in owner.enabled_notifications:
        return "skipped"
    try:
        task = await service.get_task(execution.owner_id, execution.task_id)
        project = (await service.get_project(execution.owner_id, task.project_id)).name
        prompt = task.prompt
    except service.NotFoundError:
        project, prompt = "projet supprimé", ""
    # En réponse à la carte de suivi quand il y en a une : l'alerte reste liée à sa tâche
    reply = {}
    if execution.card_message_id:
        reply["reply_parameters"] = ReplyParameters(message_id=execution.card_message_id, allow_sending_without_reply=True)
    try:
        await bot.send_message(
            chat_id=execution.owner_id, text=build_text(execution, prompt, project),
            reply_markup=build_keyboard(execution), **reply,
        )
    except Forbidden:
        logger.info("Notification Orbi Dev non remise : l'utilisateur %s a bloqué le bot", execution.owner_id)
        return "skipped"
    except TelegramError as error:
        logger.warning("Notification Orbi Dev %s en échec passager : %s", execution.id, error)
        return "retry"
    return "sent"


async def notify_pending(bot: Bot) -> int:
    """Annonce les exécutions récemment arrivées dans un état à signaler. Retourne le nombre de messages envoyés."""
    since = datetime.now(UTC) - MAX_AGE
    candidates = await Execution.find(
        {
            "status": {"$in": [s.value for s in NOTIFY_STATUSES]},
            "updated_at": {"$gte": since},
            "$expr": {"$ne": [{"$ifNull": ["$notified_status", ""]}, "$status"]},
            "notify_attempts": {"$lt": MAX_ATTEMPTS},
        }
    ).limit(BATCH).to_list()

    sent = 0
    for candidate in candidates:
        previous = candidate.notified_status
        claimed = await _claim(candidate)
        if claimed is None:
            continue
        outcome = await _announce(bot, claimed)
        if outcome == "sent":
            sent += 1
        elif outcome == "retry":
            await _release(claimed, previous)
    return sent
