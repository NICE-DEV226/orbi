"""
Orbi — Gestionnaire d'erreurs global du bot.

Sans lui, une exception dans un handler était seulement journalisée : le bouton pressé restait sans réponse
(le sablier tourne, rien ne s'affiche). L'utilisateur est maintenant prévenu et l'erreur reste dans les logs.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("orbi.bot.errors")

USER_MESSAGE = "⚠️ Une erreur est survenue. Réessayez dans un instant."


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception dans un handler", exc_info=context.error)

    if not isinstance(update, Update):
        return
    try:
        if update.callback_query:
            await update.callback_query.answer(USER_MESSAGE, show_alert=True)
        elif update.effective_message and update.effective_chat and update.effective_chat.type == "private":
            await update.effective_message.reply_text(USER_MESSAGE)
    except Exception:  # le retour d'erreur lui-même ne doit jamais lever
        logger.debug("Impossible d'informer l'utilisateur de l'erreur", exc_info=True)


def register_error_handler(application) -> None:
    application.add_error_handler(on_error)
