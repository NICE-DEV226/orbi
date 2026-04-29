"""
Orbi — Middleware de rate limiting via Redis sorted sets (sliding window).
Conforme au CdC §11.3 : implémenté avec Redis sorted sets, pas avec des compteurs simples.
"""

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from src.core.i18n import t
from src.core.redis import get_redis

logger = logging.getLogger("orbi.middleware.rate_limit")

# ── Configuration par défaut ──
DEFAULT_MAX_REQUESTS = 30  # messages par fenêtre
DEFAULT_WINDOW_SECONDS = 60  # fenêtre glissante de 60 secondes
RATE_LIMIT_KEY_PREFIX = "orbi:ratelimit:user:"


class RateLimitMiddleware:
    """
    Rate limiting par utilisateur via Redis Sorted Sets (sliding window algorithm).

    Algorithme :
    1. Supprime les entrées plus anciennes que la fenêtre
    2. Compte les entrées restantes
    3. Si le nombre dépasse le maximum, bloque la requête
    4. Sinon, ajoute la nouvelle requête au set
    """

    def __init__(
        self,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> bool:
        """
        Retourne True si la requête est autorisée, False si rate-limitée.
        """
        user = update.effective_user
        if not user:
            return True

        try:
            is_allowed = await self._check_rate_limit(user.id)
        except Exception as e:
            # En cas d'erreur Redis, on laisse passer (fail-open)
            logger.warning("Erreur rate limiting (fail-open): %s", e)
            return True

        if not is_allowed:
            await self._send_rate_limit_message(update, context)
            return False

        return True

    async def _check_rate_limit(self, telegram_id: int) -> bool:
        """
        Vérifie et met à jour le rate limit via Redis sorted set.
        Utilise un pipeline pour atomicité.
        """
        redis = get_redis()
        key = f"{RATE_LIMIT_KEY_PREFIX}{telegram_id}"
        now = time.time()
        window_start = now - self.window_seconds

        # Pipeline atomique
        pipe = redis.pipeline()

        # 1. Supprime les entrées hors fenêtre
        pipe.zremrangebyscore(key, 0, window_start)

        # 2. Compte les entrées dans la fenêtre
        pipe.zcard(key)

        # 3. Ajoute la requête actuelle
        pipe.zadd(key, {str(now): now})

        # 4. Renouvelle le TTL
        pipe.expire(key, self.window_seconds + 10)

        results = await pipe.execute()
        current_count = results[1]  # Résultat du zcard

        if current_count >= self.max_requests:
            # Rate limit atteint — supprime l'entrée qu'on vient d'ajouter
            await redis.zrem(key, str(now))
            logger.info(
                "Rate limit atteint: user=%d, count=%d/%d",
                telegram_id,
                current_count,
                self.max_requests,
            )
            return False

        return True

    async def _send_rate_limit_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Envoie un message de rate limit localisé."""
        lang = context.user_data.get("lang", "fr")
        text = t("common.rate_limited", lang)

        if update.callback_query:
            await update.callback_query.answer(text[:200], show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text(text)
