"""
Orbi — Initialisation du bot Telegram (python-telegram-bot v21).
Mode webhook en production, mode polling en développement.
Enregistre les middlewares (i18n, auth, rate limit, logging).
"""

import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, Defaults, TypeHandler

from src.bot.middlewares.auth import AuthMiddleware
from src.bot.middlewares.i18n import I18nMiddleware
from src.bot.middlewares.logging_mw import LoggingMiddleware
from src.bot.middlewares.rate_limit import RateLimitMiddleware
from src.core.config import get_settings

logger = logging.getLogger("orbi.bot")

# Instances de middlewares
_logging_mw = LoggingMiddleware()
_i18n_mw = I18nMiddleware()
_auth_mw = AuthMiddleware()
_rate_limit_mw = RateLimitMiddleware()


async def _middleware_handler(update: Update, context) -> None:
    """
    Handler global exécuté AVANT tous les autres handlers (group=-10).
    Orchestre les middlewares dans l'ordre correct :
    1. Logging (log de la requête entrante)
    2. Auth (charge/crée le User, vérifie le ban)
    3. i18n (injecte la langue et t() dans le contexte)
    4. Rate limiting (sliding window Redis)
    """
    # 1. Logging
    await _logging_mw(update, context)

    # 2. Auth — bloque si banni
    is_authorized = await _auth_mw(update, context)
    if not is_authorized:
        # Utilisateur banni — on arrête le traitement ici
        # Les handlers suivants ne seront pas exécutés via raise ApplicationHandlerStop
        from telegram.ext import ApplicationHandlerStop
        raise ApplicationHandlerStop()

    # 3. i18n — doit être après auth (utilise db_user pour la langue)
    await _i18n_mw(update, context)

    # 4. Rate limiting
    is_allowed = await _rate_limit_mw(update, context)
    if not is_allowed:
        from telegram.ext import ApplicationHandlerStop
        raise ApplicationHandlerStop()


async def create_bot_application() -> Application:
    """
    Crée et configure l'application python-telegram-bot v21.
    Enregistre les middlewares et prépare l'enregistrement des handlers par les modules.
    """
    settings = get_settings()

    # Defaults : parse_mode HTML pour tous les messages
    defaults = Defaults(parse_mode="HTML")

    builder = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .defaults(defaults)
        .concurrent_updates(True)
        .connect_timeout(10.0)
        .read_timeout(10.0)
        .write_timeout(10.0)
        .pool_timeout(10.0)
    )

    application = builder.build()

    # ── Enregistrement du middleware handler (group=-10 = exécuté en premier) ──
    application.add_handler(
        TypeHandler(Update, _middleware_handler),
        group=-10,
    )
    # ── Enregistrement des handlers ──
    from src.handlers.onboarding import register_onboarding_handlers
    from src.handlers.menu import register_menu_handlers
    from src.handlers.profile import register_profile_handlers

    # Phase 3 : Onboarding + Navigation + Profil
    register_onboarding_handlers(application)
    register_menu_handlers(application)
    register_profile_handlers(application)

    # Phase 4 : Support
    from src.handlers.support import register_support_handlers
    register_support_handlers(application)

    # Phase 5 : Commerce
    from src.handlers.commerce import register_commerce_handlers
    register_commerce_handlers(application)

    # Phase 6 : Communauté
    from src.handlers.community import register_community_handlers
    register_community_handlers(application)

    # Phase 7 : Productivité
    from src.handlers.productivity import register_productivity_handlers
    register_productivity_handlers(application)

    # Phase 8 : Développeur
    from src.handlers.developer import register_developer_handlers
    register_developer_handlers(application)
    
    # Handlers de test
    from src.handlers.test import register_test_handlers
    register_test_handlers(application)
    
    # Handlers utilitaires pour groupes
    from src.handlers.group_utils import register_group_utils_handlers
    register_group_utils_handlers(application)
    
    # Fonctionnalités avancées
    from src.handlers.admin_auth import register_admin_handlers
    register_admin_handlers(application)
    
    from src.handlers.group_management import register_group_handlers
    register_group_handlers(application)
    
    from src.handlers.developer_real import register_developer_handlers as register_real_dev_handlers
    register_real_dev_handlers(application)

    logger.info(
        "Bot Telegram initialisé (mode=%s, middlewares=4, handlers=phase3+4+5+6+7+8)",
        "webhook" if settings.use_webhook else "polling",
    )

    return application


async def start_bot(application: Application) -> None:
    """Démarre le bot selon le mode configuré."""
    settings = get_settings()

    if settings.use_webhook:
        # Mode webhook (production)
        logger.info("Démarrage en mode webhook: %s", settings.TELEGRAM_WEBHOOK_URL)
        await application.bot.set_webhook(
            url=f"{settings.TELEGRAM_WEBHOOK_URL}/webhook/telegram",
            secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
            allowed_updates=["message", "callback_query", "my_chat_member"],
        )
        await application.initialize()
        await application.start()
    else:
        # Mode polling (développement)
        logger.info("Démarrage en mode polling")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            allowed_updates=["message", "callback_query", "my_chat_member"],
            drop_pending_updates=True,
        )


async def stop_bot(application: Application) -> None:
    """Arrête le bot proprement."""
    settings = get_settings()

    if settings.use_webhook:
        await application.bot.delete_webhook()

    if application.updater and application.updater.running:
        await application.updater.stop()

    await application.stop()
    await application.shutdown()
    logger.info("Bot Telegram arrêté")
