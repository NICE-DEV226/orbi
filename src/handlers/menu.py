"""
Orbi — Handlers Menu Principal & Navigation (Phase 3 + Phase 10).
Menu principal, navigation vers les sous-menus des 5 modules avec Logo.
Conforme au CdC §2 : Menu Principal accessible depuis n'importe quel état.
"""

import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ContextTypes

from src.bot.keyboards import (
    CB_HOME,
    CB_MODULE_COMMUNITY,
    CB_MODULE_DEVELOPERS,
    CB_MODULE_PRODUCTIVITY,
    CB_MODULE_PROFILE,
    CB_MODULE_SHOP,
    CB_MODULE_SUPPORT,
    main_menu_keyboard,
)
from src.core.i18n import t

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
    """Affiche le menu principal avec le logo."""
    if update.callback_query:
        await update.callback_query.answer()

    if not context.user_data: 
        return
    lang = context.user_data.get("lang", "fr")
    # Pour s'assurer qu'il prend bien le titre
    text = t("menu.main.title", lang)
    
    # Ajouter un bouton pour ajouter le bot à un groupe
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("menu.main.support", lang), callback_data=CB_MODULE_SUPPORT),
            InlineKeyboardButton(t("menu.main.shop", lang), callback_data=CB_MODULE_SHOP),
        ],
        [
            InlineKeyboardButton(t("menu.main.community", lang), callback_data=CB_MODULE_COMMUNITY),
            InlineKeyboardButton(t("menu.main.productivity", lang), callback_data=CB_MODULE_PRODUCTIVITY),
        ],
        [
            InlineKeyboardButton(t("menu.main.developers", lang), callback_data=CB_MODULE_DEVELOPERS),
        ],
        [
            InlineKeyboardButton(t("menu.main.profile", lang), callback_data=CB_MODULE_PROFILE),
        ],
        [
            InlineKeyboardButton("👥 Ajouter à un groupe", callback_data="group:add"),
            InlineKeyboardButton("📢 Ajouter à un canal", callback_data="channel:add"),
        ],
    ])

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


async def show_shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le sous-menu Boutique avec le logo."""
    if update.callback_query:
        await update.callback_query.answer()
    if not context.user_data: 
        return
    lang = context.user_data.get("lang", "fr")

    text = f"🛒 <b>{t('commerce.menu_title', lang)}</b>"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("commerce.catalog", lang), callback_data="shop:catalog"),
            InlineKeyboardButton(t("commerce.my_orders", lang), callback_data="shop:my_orders"),
        ],
        [
            InlineKeyboardButton(t("commerce.cart", lang), callback_data="shop:cart"),
            InlineKeyboardButton(t("commerce.search", lang), callback_data="shop:search"),
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
            InlineKeyboardButton(t("community.karma", lang), callback_data="community:karma"),
        ],
        [InlineKeyboardButton(t("community.rules", lang), callback_data="community:rules")],
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
            InlineKeyboardButton(t("productivity.new_task", lang), callback_data="prod:new_task"),
            InlineKeyboardButton(t("productivity.my_tasks", lang), callback_data="prod:my_tasks"),
        ],
        [
            InlineKeyboardButton(t("productivity.new_note", lang), callback_data="prod:new_note"),
            InlineKeyboardButton(t("productivity.my_notes", lang), callback_data="prod:my_notes"),
        ],
        [
            InlineKeyboardButton("🍅 Focus", callback_data="prod:timer_menu"),
            InlineKeyboardButton("🌐 Translate", callback_data="prod:translate"),
        ],
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
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("developers.api_keys", lang), callback_data="dev:api_keys"),
            InlineKeyboardButton(t("developers.webhooks", lang), callback_data="dev:github"),
        ],
        [
            InlineKeyboardButton(t("developers.sandbox", lang), callback_data="dev:sandbox"),
            InlineKeyboardButton(t("developers.logs", lang), callback_data="dev:logs"),
        ],
        [
            InlineKeyboardButton(t("developers.stats", lang), callback_data="dev:stats"),
            InlineKeyboardButton(t("developers.docs", lang), callback_data="dev:docs"),
        ],
        [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
    ])

    await send_or_edit_menu(update, context, text, keyboard)


def register_menu_handlers(application) -> None:
    """Enregistre les handlers de navigation du menu principal."""
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern=f"^{CB_HOME}$"))
    application.add_handler(CallbackQueryHandler(show_support_menu, pattern=f"^{CB_MODULE_SUPPORT}$"))
    application.add_handler(CallbackQueryHandler(show_shop_menu, pattern=f"^{CB_MODULE_SHOP}$"))
    application.add_handler(CallbackQueryHandler(show_community_menu, pattern=f"^{CB_MODULE_COMMUNITY}$"))
    application.add_handler(CallbackQueryHandler(show_productivity_menu, pattern=f"^{CB_MODULE_PRODUCTIVITY}$"))
    application.add_handler(CallbackQueryHandler(show_developers_menu, pattern=f"^{CB_MODULE_DEVELOPERS}$"))
    
    # Callbacks pour ajouter le bot à des groupes/canaux
    from src.handlers.group_utils import add_to_group_command, add_to_channel_command
    
    application.add_handler(CallbackQueryHandler(
        lambda u, c: add_to_group_command(u, c), 
        pattern=r"^group:add$"
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: add_to_channel_command(u, c), 
        pattern=r"^channel:add$"
    ))
    
    # Callbacks pour les fonctionnalités avancées
    # Admin - déjà géré par register_admin_handlers()
    # Groupes - déjà géré par register_group_handlers()
    # Développeurs - déjà géré par register_real_dev_handlers()
    
    logger.info("Handlers menu enregistrés")
