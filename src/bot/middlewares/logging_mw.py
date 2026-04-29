"""
Orbi — Middleware de logging structuré pour chaque update Telegram.
Logge les informations pertinentes pour le debugging et le monitoring.
"""

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("orbi.middleware.request")


class LoggingMiddleware:
    """
    Middleware de logging structuré pour le bot Telegram.

    Logge pour chaque update :
    - Type d'update (message, callback_query, etc.)
    - User (telegram_id, username)
    - Contenu résumé (texte tronqué, callback_data)
    - Durée de traitement (si utilisé avec un wrapper)
    """

    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Logge les informations de l'update."""
        user = update.effective_user
        user_info = f"user={user.id}" if user else "user=system"

        if user and user.username:
            user_info += f" (@{user.username})"

        # Détection du type d'update
        if update.callback_query:
            data = update.callback_query.data or "?"
            logger.info(
                "📥 CALLBACK │ %s │ data=%s",
                user_info,
                data,
            )
        elif update.message:
            msg = update.message
            if msg.text:
                text_preview = msg.text[:50] + "..." if len(msg.text) > 50 else msg.text
                logger.info(
                    "📥 MESSAGE  │ %s │ text=%s",
                    user_info,
                    repr(text_preview),
                )
            elif msg.voice:
                logger.info(
                    "📥 VOICE    │ %s │ duration=%ds",
                    user_info,
                    msg.voice.duration,
                )
            elif msg.photo:
                logger.info("📥 PHOTO    │ %s", user_info)
            elif msg.document:
                logger.info(
                    "📥 DOCUMENT │ %s │ file=%s",
                    user_info,
                    msg.document.file_name,
                )
            else:
                logger.info("📥 OTHER    │ %s", user_info)
        elif update.my_chat_member:
            logger.info(
                "📥 MEMBER   │ %s │ status=%s",
                user_info,
                update.my_chat_member.new_chat_member.status,
            )
        else:
            logger.debug("📥 UPDATE   │ %s │ type=unknown", user_info)

        # Stocke le timestamp de début pour le calcul de durée
        context.user_data["_request_start"] = time.monotonic()


def log_handler_complete(
    handler_name: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Utilitaire pour loguer la fin d'un handler avec sa durée."""
    start = context.user_data.get("_request_start")
    if start:
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "✅ DONE     │ handler=%s │ duration=%.1fms",
            handler_name,
            duration_ms,
        )
