"""
Orbi — Affichage d'un écran du bot en réponse à un bouton.

Le menu principal est un message photo (logo + légende). Telegram refuse `editMessageText` sur un message sans texte
(« There is no text in the message to edit ») : un bouton d'un écran qui édite le texte restait donc sans réponse quand
on l'ouvrait depuis ce menu. `edit_screen` couvre les deux cas.
"""

import logging
from typing import Any

from telegram import CallbackQuery
from telegram.error import BadRequest

logger = logging.getLogger("orbi.bot.screen")


def _is_photo_message(query: CallbackQuery) -> bool:
    message = query.message
    photo = getattr(message, "photo", None)
    return isinstance(photo, (tuple, list)) and bool(photo)


async def edit_screen(query: CallbackQuery, text: str, reply_markup: Any = None, **kwargs: Any) -> None:
    """Remplace l'écran affiché sous le bouton pressé, que le message soit un texte ou une photo."""
    if _is_photo_message(query):
        # Une légende est limitée à 1024 caractères : on remplace la photo par un message texte.
        chat_id = query.message.chat_id
        try:
            await query.delete_message()
        except BadRequest as e:
            logger.debug("Suppression du message photo impossible (ignorée) : %s", e)
        await query.get_bot().send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, **kwargs)
        return

    try:
        await query.edit_message_text(text, reply_markup=reply_markup, **kwargs)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return  # même contenu : rien à faire, le bouton a bien répondu
        raise
