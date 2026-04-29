"""
Orbi — Middleware i18n pour python-telegram-bot.
Détecte la langue de l'utilisateur et injecte la fonction t() dans le contexte.
"""

import logging
from typing import Any

from telegram import Update
from telegram.ext import BaseHandler, ContextTypes

from src.core.i18n import detect_language, t as translate

logger = logging.getLogger("orbi.middleware.i18n")


class I18nMiddleware:
    """
    Middleware d'internationalisation.

    - Au premier contact : détecte la langue Telegram et la stocke.
    - Pour chaque update : injecte `context.user_data["lang"]` et
      `context.user_data["t"]` (fonction de traduction pré-configurée).
    """

    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Appelé comme post_init ou via un type_handler pour chaque update."""
        user = update.effective_user
        if not user:
            return

        # Récupère la langue depuis le user_data (session) ou la DB
        lang = context.user_data.get("lang")

        if not lang:
            # Essaye de charger depuis la DB via le user stocké par auth middleware
            db_user = context.user_data.get("db_user")
            if db_user and db_user.language:
                # L'utilisateur a déjà choisi une langue
                lang = db_user.language
            else:
                # L'utilisateur n'a pas encore choisi de langue, utiliser le français par défaut
                # pour les messages système mais ne pas la sauvegarder
                lang = "fr"

            context.user_data["lang"] = lang

        # Injecte une fonction t() pré-configurée avec la langue
        context.user_data["t"] = lambda key, **kwargs: translate(key, lang, **kwargs)


def get_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Utilitaire : récupère la langue depuis le contexte."""
    return context.user_data.get("lang", "fr")


def i18n(context: ContextTypes.DEFAULT_TYPE, key: str, **kwargs: Any) -> str:
    """Utilitaire : traduit une clé avec le contexte courant."""
    lang = get_lang(context)
    return translate(key, lang, **kwargs)
