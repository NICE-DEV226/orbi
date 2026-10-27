"""
Orbi — Handlers Menu Principal & Navigation (Phase 3 + Phase 10).
Menu principal, navigation vers les sous-menus des 5 modules avec Logo.
Conforme au CdC §2 : Menu Principal accessible depuis n'importe quel état.
"""

import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ContextTypes

from src.bot.keyboards import (
    CB_HOME,
    CB_MODULE_COMMUNITY,
    CB_MODULE_DEVELOPERS,
    CB_MODULE_PRODUCTIVITY,
    CB_MODULE_SUPPORT,
    CB_MORE,
    main_menu_keyboard,
    orbi_dev_button,
)
from src.core.config import get_settings
from src.core.i18n import t
from src.orbi_dev.access import can_use_orbi_dev

logger = logging.getLogger("orbi.handlers.menu")

# Chemin vers le logo à la racine
LOGO_PATH = "logo.png"


async def send_or_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup) -> None:
    """Helper pour envoyer le menu avec le logo en image."""
    query = update.callback_query

    if query:
        has_photo = bool(query.message.photo)
        if has_photo:
            try:
                await query.edit_message_caption(caption=text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                return
            except BadRequest as e:
                logger.debug(f"Erreur edit_message_caption (ignorée) : {e}")
                return # Contenu identique ou erreur mineure
        else:
            try:
                await query.delete_message()
            except BadRequest:
                pass
            chat_id = query.message.chat_id
    else:
        chat_id = update.effective_chat.id

    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    « Accueil ». Pour un administrateur, c'est Orbi Dev (état des tâches, nouvelle tâche) ; les autres modules sont
    derrière « Plus ». Les autres utilisateurs gardent le menu des modules.
    """
    if can_use_orbi_dev((context.user_data or {}).get("db_user")):
        from src.handlers.dev_hub import show_home
        await show_home(update, context)
        return
    await show_modules_menu(update, context)


async def show_modules_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menu des modules (Support, Productivité, Développeurs, Profil…) avec le logo."""
    if update.callback_query:
        await update.callback_query.answer()

    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")
    # Pour s'assurer qu'il prend bien le titre
    text = t("menu.main.title", lang)

    keyboard = main_menu_keyboard(lang, is_admin=bool(getattr(context.user_data.get("db_user"), "is_admin", False)))

    await send_or_edit_menu(update, context, text, keyboard)


async def show_support_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le sous-menu Support avec le logo."""
    if update.callback_query:
        await update.callback_query.answer()
    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")

    text = f"⚙️ <b>{t('support.menu_title', lang)}</b>"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("support.new_ticket", lang), callback_data="support:new_ticket"),
            InlineKeyboardButton(t("support.my_tickets", lang), callback_data="support:my_tickets"),
        ],
        [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
    ])

    await send_or_edit_menu(update, context, text, keyboard)


async def show_community_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le sous-menu Communauté avec le logo."""
    if update.callback_query:
        await update.callback_query.answer()
    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")

    text = f"👥 <b>{t('community.menu_title', lang)}</b>"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("community.polls", lang), callback_data="community:polls"),
            InlineKeyboardButton(t("community.karma", lang), callback_data="community:leaderboard"),
        ],
        [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
    ])

    await send_or_edit_menu(update, context, text, keyboard)


async def show_productivity_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le sous-menu Productivité avec le logo."""
    if update.callback_query:
        await update.callback_query.answer()
    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")

    text = f"🧠 <b>{t('productivity.menu_title', lang)}</b>"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("productivity.new_task", lang), callback_data="prod:task_new"),
            InlineKeyboardButton(t("productivity.my_tasks", lang), callback_data="prod:tasks"),
        ],
        [
            InlineKeyboardButton(t("productivity.new_note", lang), callback_data="prod:note_new"),
            InlineKeyboardButton(t("productivity.my_notes", lang), callback_data="prod:notes"),
        ],
        [InlineKeyboardButton("🍅 Focus", callback_data="prod:focus")],
        [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
    ])

    await send_or_edit_menu(update, context, text, keyboard)


async def show_developers_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le sous-menu Développeurs avec le logo."""
    if update.callback_query:
        await update.callback_query.answer()
    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")

    text = f"🛠️ <b>{t('developers.menu_title', lang)}</b>\n\n<i>Espace administrateur / Développeur</i>"

    rows = [
        [InlineKeyboardButton(t("developers.webhooks", lang), callback_data="dev:github")],
        [
            InlineKeyboardButton(t("developers.logs", lang), callback_data="dev:logs"),
            InlineKeyboardButton(t("developers.stats", lang), callback_data="dev:stats"),
        ],
    ]
    mini_app = orbi_dev_button()
    if mini_app:
        rows.append([mini_app])
    rows.append([InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)])
    keyboard = InlineKeyboardMarkup(rows)

    await send_or_edit_menu(update, context, text, keyboard)


def register_menu_handlers(application) -> None:
    """Enregistre les handlers de navigation du menu principal."""
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern=f"^{CB_HOME}$"))
    application.add_handler(CallbackQueryHandler(show_modules_menu, pattern=f"^{CB_MORE}$"))
    application.add_handler(CallbackQueryHandler(show_support_menu, pattern=f"^{CB_MODULE_SUPPORT}$"))
    application.add_handler(CallbackQueryHandler(show_productivity_menu, pattern=f"^{CB_MODULE_PRODUCTIVITY}$"))
    application.add_handler(CallbackQueryHandler(show_developers_menu, pattern=f"^{CB_MODULE_DEVELOPERS}$"))

    if get_settings().ENABLE_COMMUNITY:
        application.add_handler(CallbackQueryHandler(show_community_menu, pattern=f"^{CB_MODULE_COMMUNITY}$"))

        # Callbacks pour ajouter le bot à des groupes/canaux
        from src.handlers.group_utils import add_to_channel_command, add_to_group_command

        application.add_handler(CallbackQueryHandler(
            lambda u, c: add_to_group_command(u, c),
            pattern=r"^group:add$"
        ))
        application.add_handler(CallbackQueryHandler(
            lambda u, c: add_to_channel_command(u, c),
            pattern=r"^channel:add$"
        ))

    logger.info("Handlers menu enregistrés")
