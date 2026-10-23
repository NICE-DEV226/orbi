"""
Orbi — Service de notifications Telegram (Phase 4).
Gère l'envoi de messages avec retry automatique en cas de RetryAfter.
Conforme au CdC §11.3 : gestion RetryAfter sans crash.
"""

import asyncio
import logging

from telegram import Bot, InlineKeyboardMarkup
from telegram.error import Forbidden, RetryAfter, TelegramError

logger = logging.getLogger("orbi.services.notification")

MAX_RETRIES = 3


async def send_notification(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str = "HTML",
    max_retries: int = MAX_RETRIES,
) -> bool:
    """
    Envoie un message Telegram avec retry automatique.
    Gère RetryAfter (429) en attendant le délai indiqué par l'API.
    Retourne True si envoyé, False sinon.
    """
    for attempt in range(1, max_retries + 1):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
            return True

        except RetryAfter as e:
            wait_time = e.retry_after + 1
            logger.warning(
                "RetryAfter: chat=%d, attempt=%d/%d, wait=%ds",
                chat_id, attempt, max_retries, wait_time,
            )
            if attempt < max_retries:
                await asyncio.sleep(wait_time)
            else:
                logger.error("RetryAfter épuisé après %d tentatives: chat=%d", max_retries, chat_id)
                return False

        except Forbidden:
            logger.warning("Bot bloqué par l'utilisateur: chat=%d", chat_id)
            return False

        except TelegramError as e:
            logger.error(
                "Erreur Telegram: chat=%d, attempt=%d/%d, error=%s",
                chat_id, attempt, max_retries, e,
            )
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)  # Backoff exponentiel
            else:
                return False

    return False


async def send_admin_alert(
    bot: Bot,
    admin_chat_id: int,
    title: str,
    details: str,
) -> bool:
    """Envoie une alerte à l'admin (SLA breach, erreurs critiques, etc.)."""
    text = f"🚨 <b>{title}</b>\n\n{details}"
    return await send_notification(bot, admin_chat_id, text)
