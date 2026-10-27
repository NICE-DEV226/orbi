"""
Orbi Dev — Carte de suivi d'une exécution dans Telegram.

Au lancement d'une tâche depuis le bot, un message unique (« la carte ») est posté. Le worker l'édite à chaque
changement d'état : plus besoin d'ouvrir une page pour voir où en est l'agent, et la conversation ne se remplit pas de
messages intermédiaires. Les modifications sont silencieuses ; l'alerte sonore reste celle de `notifier.py`, envoyée en
réponse à la carte quand l'exécution se termine ou demande de l'attention.

Mêmes garanties que le notifier : l'état en base reste la vérité, la mise à jour d'un état est prise de façon atomique
(`card_status`), un échec passager est réessayé (5 fois au plus), une carte supprimée par l'utilisateur est abandonnée.
"""

import logging
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from telegram import Bot, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, TelegramError

from src.core.text import esc
from src.orbi_dev import service
from src.orbi_dev.look import progress, quote
from src.orbi_dev.models import Execution
from src.orbi_dev.notifier import build_keyboard, first_line
from src.orbi_dev.present import STATUS_EMOJI, STATUS_INFO, ago, provider_name
from src.orbi_dev.state import ExecutionStatus, is_terminal

logger = logging.getLogger("orbi.dev.cards")

MAX_AGE = timedelta(hours=6)
MAX_ATTEMPTS = 5
BATCH = 50


def render_text(execution: Execution, prompt: str, project: str) -> str:
    """Texte de la carte (HTML Telegram : tout ce qui vient de l'extérieur est échappé)."""
    status = ExecutionStatus(execution.status)
    label, sentence, _tone, _group = STATUS_INFO[status]
    if status == ExecutionStatus.SUCCEEDED:
        detail = first_line(execution.result_summary or "", 300)
    elif is_terminal(status) or status == ExecutionStatus.NEEDS_ATTENTION:
        detail = first_line(execution.error_message or "", 300) or sentence
    else:
        detail = sentence
    lines = [
        f"{STATUS_EMOJI[status]} <b>{label}</b>  {progress(status)}",
        f"<b>{esc(project)}</b> · {esc(provider_name(execution.provider))}",
        "",
        quote(esc(first_line(prompt, 160)), expandable=False),
    ]
    if detail:
        lines.append(esc(detail))
    lines += ["", f"<i>Lancée {ago(execution.created_at)} · tentative {execution.attempt}</i>"]
    return "\n".join(lines)


def render_keyboard(execution: Execution) -> InlineKeyboardMarkup | None:
    """Pendant l'exécution : Ouvrir et Actualiser. Ensuite, seulement les liens : les actions sont dans l'alerte."""
    return build_keyboard(execution, with_action=not is_terminal(ExecutionStatus(execution.status)))


async def _context(execution: Execution) -> tuple[str, str]:
    """(consigne, nom du projet) ; valeurs de repli si la tâche ou le projet ont disparu."""
    try:
        task = await service.get_task(execution.owner_id, execution.task_id)
    except service.NotFoundError:
        return "", "projet supprimé"
    try:
        project = (await service.get_project(execution.owner_id, task.project_id)).name
    except service.NotFoundError:
        project = "projet supprimé"
    return task.prompt, project


async def render(execution: Execution) -> tuple[str, InlineKeyboardMarkup | None]:
    prompt, project = await _context(execution)
    return render_text(execution, prompt, project), render_keyboard(execution)


async def attach(execution: Execution, chat_id: int, message_id: int) -> None:
    """Fait d'un message existant (l'écran de confirmation du bot) la carte de cette exécution."""
    await Execution.get_pymongo_collection().update_one(
        {"_id": execution.id},
        {"$set": {"card_chat_id": chat_id, "card_message_id": message_id, "card_status": execution.status.value}},
    )


async def post_card(bot: Bot, execution: Execution) -> None:
    """Poste une carte neuve (nouvelle tentative lancée depuis une alerte)."""
    text, keyboard = await render(execution)
    message = await bot.send_message(chat_id=execution.owner_id, text=text, reply_markup=keyboard)
    await attach(execution, message.chat_id, message.message_id)


async def edit_card(bot: Bot, execution: Execution) -> str:
    """Retourne 'done', 'gone' (carte supprimée ou bot bloqué : on arrête) ou 'retry' (échec passager)."""
    text, keyboard = await render(execution)
    try:
        await bot.edit_message_text(
            chat_id=execution.card_chat_id, message_id=execution.card_message_id, text=text, reply_markup=keyboard
        )
    except BadRequest as error:
        message = str(error).lower()
        if "message is not modified" in message:
            return "done"
        if "not found" in message or "can't be edited" in message:
            return "gone"
        logger.warning("Carte %s non éditée : %s", execution.id, error)
        return "retry"
    except Forbidden:
        return "gone"
    except TelegramError as error:
        logger.warning("Carte %s en échec passager : %s", execution.id, error)
        return "retry"
    return "done"


async def _claim(execution: Execution) -> Execution | None:
    document = await Execution.get_pymongo_collection().find_one_and_update(
        {"_id": execution.id, "status": execution.status.value, "card_status": {"$ne": execution.status.value}},
        {"$set": {"card_status": execution.status.value}},
        return_document=ReturnDocument.AFTER,
    )
    return await Execution.get(document["_id"]) if document else None


async def update_cards(bot: Bot) -> int:
    """Met à jour les cartes dont l'état a changé. Retourne le nombre de cartes éditées."""
    since = datetime.now(UTC) - MAX_AGE
    candidates = await Execution.find(
        {
            "card_message_id": {"$ne": None},
            "updated_at": {"$gte": since},
            "$expr": {"$ne": [{"$ifNull": ["$card_status", ""]}, "$status"]},
            "card_attempts": {"$lt": MAX_ATTEMPTS},
        }
    ).limit(BATCH).to_list()

    edited = 0
    collection = Execution.get_pymongo_collection()
    for candidate in candidates:
        previous = candidate.card_status
        claimed = await _claim(candidate)
        if claimed is None:
            continue
        outcome = await edit_card(bot, claimed)
        if outcome == "done":
            edited += 1
        elif outcome == "gone":
            await collection.update_one({"_id": claimed.id}, {"$set": {"card_message_id": None}})
        else:
            await collection.update_one(
                {"_id": claimed.id, "card_status": claimed.status.value},
                {"$set": {"card_status": previous}, "$inc": {"card_attempts": 1}},
            )
    return edited
