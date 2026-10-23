"""
Orbi — Middleware d'authentification pour python-telegram-bot.
Vérifie les rôles, gère les bans, et crée automatiquement les utilisateurs.
"""

import logging
from datetime import UTC, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.i18n import t
from src.models.user import User, UserRole

logger = logging.getLogger("orbi.middleware.auth")

# Cache TTL pour éviter de requêter la DB à chaque message
_USER_CACHE_TTL_SECONDS = 60


class AuthMiddleware:
    """
    Middleware d'authentification et d'autorisation.

    - Crée automatiquement un User en DB au premier contact.
    - Charge le User depuis la DB (avec cache en mémoire via user_data).
    - Bloque les utilisateurs bannis avec un message localisé.
    - Met à jour last_active_at.
    """

    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> bool:
        """
        Retourne True si l'utilisateur est autorisé, False s'il est bloqué (banni).
        """
        user = update.effective_user
        if not user:
            return True  # Updates système sans user (channel posts, etc.)

        # ── Chargement / Création du User ──
        db_user = await self._get_or_create_user(user, context)
        if context.user_data is not None:
            context.user_data["db_user"] = db_user

        # ── Vérification du ban ──
        if db_user.is_banned:
            await self._send_ban_message(update, db_user)
            return False

        # ── Mise à jour de l'activité ──
        db_user.touch()
        await db_user.save()

        return True

    async def _get_or_create_user(
        self,
        tg_user,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> User:
        """Récupère ou crée un utilisateur en DB avec cache dans user_data."""
        # Cache dans user_data (évite un appel DB par message)
        cached = context.user_data.get("db_user")
        cache_time = context.user_data.get("db_user_cached_at", 0)
        now_ts = datetime.now(UTC).timestamp()

        if cached and (now_ts - cache_time) < _USER_CACHE_TTL_SECONDS:
            # Met à jour les infos Telegram qui peuvent changer
            if cached.first_name != tg_user.first_name or cached.username != tg_user.username:
                cached.first_name = tg_user.first_name or ""
                cached.username = tg_user.username
                cached.last_name = tg_user.last_name
            return cached

        # Cherche en DB
        db_user = await User.find_one(User.telegram_id == tg_user.id)

        if db_user is None:
            # Premier contact — Création automatique SANS langue
            db_user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name or "",
                last_name=tg_user.last_name,
                language=None,  # Sera défini lors de la sélection explicite
            )
            await db_user.insert()
            logger.info(
                "Nouvel utilisateur créé: %s (telegram_id=%d, lang=non défini)",
                db_user.display_name,
                tg_user.id,
            )

        # Mise à jour du cache
        if context.user_data is not None:
            context.user_data["db_user"] = db_user
            context.user_data["db_user_cached_at"] = now_ts

        return db_user

    async def _send_ban_message(self, update: Update, db_user: User) -> None:
        """Affiche le message de ban à l'utilisateur banni."""
        lang = db_user.language
        reason = db_user.ban_reason or "Non spécifiée"

        text = t("common.banned", lang, reason=reason)

        keyboard = []
        # Option de contacter le support (configurable)
        keyboard.append([
            InlineKeyboardButton(
                t("common.banned_contact", lang),
                callback_data="banned_contact_support",
            )
        ])

        if update.callback_query:
            await update.callback_query.answer(
                t("common.banned", lang, reason=reason)[:200],
                show_alert=True,
            )
        elif update.effective_message:
            await update.effective_message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )


def require_role(*roles: UserRole):
    """
    Décorateur pour les handlers nécessitant un rôle spécifique.

    Usage:
        @require_role(UserRole.ADMIN, UserRole.SUPERADMIN)
        async def admin_handler(update, context):
            ...
    """

    def decorator(handler_func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            db_user: User | None = context.user_data.get("db_user")

            if not db_user or db_user.role not in roles:
                lang = context.user_data.get("lang", "fr")
                if update.callback_query:
                    await update.callback_query.answer(
                        t("errors.forbidden", lang),
                        show_alert=True,
                    )
                elif update.effective_message:
                    await update.effective_message.reply_text(t("errors.forbidden", lang))
                return

            return await handler_func(update, context, *args, **kwargs)

        # Préserve les métadonnées
        wrapper.__name__ = handler_func.__name__
        wrapper.__doc__ = handler_func.__doc__
        return wrapper

    return decorator
