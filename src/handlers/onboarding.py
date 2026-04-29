"""
Orbi — Handlers Onboarding (Phase 3).
/start, sélection de langue, message de bienvenue.
Conforme au CdC §2 : Premier contact + Message de bienvenue + Navigation.
"""

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from src.bot.keyboards import (
    CB_LANG_AR,
    CB_LANG_EN,
    CB_LANG_FR,
    language_selector_keyboard,
    main_menu_keyboard,
)
from src.core.i18n import t
from src.models.user import User

logger = logging.getLogger("orbi.handlers.onboarding")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler pour /start.
    - TOUJOURS demander la langue au premier contact
    - Utilisateur existant : vérifier si la langue est déjà définie
    """
    if not context.user_data: return
    db_user: User = context.user_data.get("db_user")
    user = update.effective_user

    # Si l'utilisateur n'a pas de langue définie en base, demander de choisir
    if not db_user or not db_user.language:
        logger.info("Premier contact pour telegram_id=%d - demande de langue", user.id)
        await update.message.reply_text(
            t("onboarding.language_select"),
            reply_markup=language_selector_keyboard(),
        )
        return

    # Utilisateur avec langue déjà définie
    lang = db_user.language
    context.user_data["lang"] = lang
    context.user_data["_onboarded"] = True
    name = db_user.display_name

    # Vérifier si c'est la première fois qu'il utilise /start
    total_interactions = (db_user.total_orders or 0) + (db_user.total_tickets or 0)
    
    if total_interactions == 0:
        # Premier vrai contact avec langue déjà définie
        text = t("onboarding.welcome", lang, name=name)
    else:
        # Utilisateur qui revient
        text = t("onboarding.welcome_back", lang, name=name)

    from src.handlers.menu import send_or_edit_menu
    await send_or_edit_menu(update, context, text, main_menu_keyboard(lang))


async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback handler : l'utilisateur a choisi sa langue via le sélecteur.
    Sauvegarde la langue, affiche la confirmation puis le menu principal.
    """
    query = update.callback_query
    await query.answer()

    if not context.user_data: return
    # Extraire la langue du callback_data (lang:fr → fr)
    lang = query.data.split(":")[1]
    db_user: User = context.user_data.get("db_user")

    if db_user:
        # Sauvegarde en DB
        db_user.language = lang
        db_user.touch()
        await db_user.save()

    # Met à jour le contexte
    context.user_data["lang"] = lang
    context.user_data["t"] = lambda key, **kwargs: t(key, lang, **kwargs)
    context.user_data["_onboarded"] = True

    name = db_user.display_name if db_user else update.effective_user.first_name

    # Bienvenue dans la nouvelle langue + menu
    text = t("onboarding.welcome", lang, name=name)

    from src.handlers.menu import send_or_edit_menu
    await send_or_edit_menu(update, context, text, main_menu_keyboard(lang))


def register_onboarding_handlers(application) -> None:
    """Enregistre les handlers d'onboarding dans l'application bot."""
    # /start command
    application.add_handler(CommandHandler("start", start_command))

    # Sélection de langue (onboarding)
    application.add_handler(
        CallbackQueryHandler(language_selected, pattern=f"^({CB_LANG_FR}|{CB_LANG_EN}|{CB_LANG_AR})$")
    )

    logger.info("Handlers onboarding enregistrés")
