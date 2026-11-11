"""
Orbi Dev dans Telegram — mode « conversation » avec l'agent (ADR-0010).

« Discuter » sur une carte arme le mode : chaque texte libre est alors transmis à l'exécution la
plus récemment active (résolution à chaque envoi, voir `orbi_dev.chat`). Les réponses de l'agent
sont poussées par le worker. « Quitter la discussion » (ou un autre parcours) rend la main.
"""

import logging

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.text import esc
from src.orbi_dev import chat as dev_chat
from src.orbi_dev import runner, service
from src.orbi_dev.connectors.base import ConnectorError

from .common import CB_CHAT_END, authorize, button, clear_draft, show

logger = logging.getLogger("orbi.handlers.dev_hub.chat")

CHAT_HINT = (
    "<b>Mode conversation activé.</b> Écrivez simplement : chaque message part à l'agent "
    "le plus récemment actif. Ses réponses arrivent ici automatiquement."
)


async def start_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback « Discuter » : arme le mode conversation pour ce propriétaire."""
    owner = await authorize(update, context)
    if owner is None:
        return
    execution_id = (update.callback_query.data or "").removeprefix("dv:cht:")
    anchor = await dev_chat.anchor_for(owner, execution_id)
    await dev_chat.enable(owner, execution_id=execution_id, anchor=anchor)
    clear_draft(context)
    await show(
        update,
        CHAT_HINT + "\n<i>« Quitter la discussion » ou un autre parcours pour arrêter.</i>",
        InlineKeyboardMarkup([[button("Quitter la discussion", CB_CHAT_END)]]),
    )


async def exit_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    await dev_chat.disable(owner)
    clear_draft(context)
    await show(update, "<b>Discussion terminée.</b> Le mode conversation est désactivé.")


async def handle_chat_text(update: Update, context: ContextTypes.DEFAULT_TYPE, owner: int, text: str) -> None:
    """Texte libre en mode conversation : routé vers l'agent le plus récemment actif."""
    execution = await dev_chat.resolve_target(owner)
    if execution is None:
        await update.message.reply_text(
            "<b>Aucun agent en discussion.</b> Lancez ou reprenez une tâche, ou quittez le mode "
            "avec « Quitter la discussion »."
        )
        return
    try:
        await runner.send_input_to_execution(owner, str(execution.id), text)
    except (service.NotFoundError, service.ConflictError, ValueError, ConnectorError) as e:
        if isinstance(e, service.NotFoundError):
            await dev_chat.disable(owner)
            await update.message.reply_text("Discussion terminée : l'exécution n'existe plus.")
            return
        detail = e.message if isinstance(e, ConnectorError) else str(e)
        await update.message.reply_text(f"<b>Message non transmis.</b> {esc(detail)}")
        return
    except Exception:
        logger.exception("Envoi du message de conversation en échec")
        await update.message.reply_text("<b>Message non transmis.</b> Réessayez dans un instant.")
        return
    # Succès volontairement silencieux : l'agent répondra dans le fil, poussé par le worker —
    # comme une vraie conversation, pas un accusé de réception à chaque message.
