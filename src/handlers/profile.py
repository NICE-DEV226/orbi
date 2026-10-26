"""
Orbi — Handlers Profil Utilisateur (Phase 3).
Page profil, changement de langue, notifications, fuseau horaire, statistiques.
Conforme au CdC §2 : Mon Profil.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from src.bot.keyboards import (
    CB_MODULE_PROFILE,
    CB_NOTIF_TOGGLE_PREFIX,
    CB_PROFILE_CHANGE_LANG,
    CB_PROFILE_MORNING_BRIEF,
    CB_PROFILE_NOTIFICATIONS,
    CB_PROFILE_STATS,
    CB_PROFILE_TIMEZONE,
    profile_keyboard,
)
from src.bot.screen import edit_screen
from src.core.config import get_settings
from src.core.i18n import t
from src.core.i18n import t as translate_func
from src.core.text import esc
from src.models.user import NotificationPreferences, User

logger = logging.getLogger("orbi.handlers.profile")

# Mapping des langues pour l'affichage
LANG_LABELS = {"fr": "🇫🇷 Français", "en": "🇬🇧 English", "ar": "🇸🇦 العربية"}
ROLE_LABELS = {
    "fr": {"user": "Utilisateur", "agent": "Agent", "admin": "Administrateur", "superadmin": "Super Admin"},
    "en": {"user": "User", "agent": "Agent", "admin": "Administrator", "superadmin": "Super Admin"},
    "ar": {"user": "مستخدم", "agent": "وكيل", "admin": "مسؤول", "superadmin": "مسؤول أعلى"},
}


def _karma_line(lang: str, db_user: User) -> str:
    """Le karma n'existe que si le module Communauté est activé."""
    if not get_settings().ENABLE_COMMUNITY:
        return ""
    return f"\n{t('community.karma', lang)} : {db_user.karma_points}"


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la page profil de l'utilisateur."""
    if update.callback_query:
        await update.callback_query.answer()

    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    if not db_user:
        if update.callback_query:
            await edit_screen(update.callback_query, translate_func("common.error", lang))
        else:
            await update.effective_message.reply_text(translate_func("common.error", lang))
        return

    role_label = ROLE_LABELS.get(lang, ROLE_LABELS["fr"]).get(db_user.role, db_user.role)
    joined = db_user.created_at.strftime("%d/%m/%Y")

    text = f"👤 **{translate_func('profile.title', lang)}**\n\n" + translate_func(
        "profile.info",
        lang,
        name=esc(db_user.display_name),
        lang_code=LANG_LABELS.get(db_user.language, db_user.language),
        role=role_label,
        joined=joined,
        tickets=str(db_user.total_tickets),
    )

    text += _karma_line(lang, db_user)

    if update.callback_query:
        await edit_screen(update.callback_query, text, reply_markup=profile_keyboard(lang))
    else:
        await update.effective_message.reply_text(text, reply_markup=profile_keyboard(lang))


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le sélecteur de langue depuis le profil."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")

    # Ajouter un bouton annuler au sélecteur
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇫🇷 Français", callback_data="profile_lang:fr"),
            InlineKeyboardButton("🇬🇧 English", callback_data="profile_lang:en"),
            InlineKeyboardButton("🇸🇦 العربية", callback_data="profile_lang:ar"),
        ],
        [InlineKeyboardButton(t("common.cancel", lang), callback_data=CB_MODULE_PROFILE)],
    ])

    await edit_screen(
        query,
        t("profile.change_language", lang),
        reply_markup=keyboard,
    )


async def language_changed_from_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback : l'utilisateur a changé sa langue depuis le profil."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    new_lang = query.data.split(":")[1]  # profile_lang:fr → fr
    db_user: User = context.user_data.get("db_user")

    if db_user:
        db_user.language = new_lang
        db_user.touch()
        await db_user.save()

    # Met à jour le contexte
    context.user_data["lang"] = new_lang
    context.user_data["t"] = lambda key, **kwargs: t(key, new_lang, **kwargs)

    # Confirmation dans la nouvelle langue + retour au profil
    text = t("profile.language_changed", new_lang)

    # Réaffiche le profil dans la nouvelle langue
    role_label = ROLE_LABELS.get(new_lang, ROLE_LABELS["fr"]).get(db_user.role, db_user.role)
    joined = db_user.created_at.strftime("%d/%m/%Y")

    text += "\n\n" + t("profile.title", new_lang) + "\n\n" + t(
        "profile.info",
        new_lang,
        name=esc(db_user.display_name),
        lang=LANG_LABELS.get(new_lang, new_lang),
        role=role_label,
        joined=joined,
        tickets=str(db_user.total_tickets),
    )

    text += _karma_line(new_lang, db_user)

    await edit_screen(query, text, reply_markup=profile_keyboard(new_lang))


async def show_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les préférences de notifications avec toggles."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    enabled = db_user.enabled_notifications if db_user else []

    # Labels par type de notification
    notif_labels = {
        "fr": {
            NotificationPreferences.TICKET_REPLIES: "🎧 Réponses tickets",
            NotificationPreferences.COMMUNITY_ANNOUNCEMENTS: "📢 Annonces communauté",
            NotificationPreferences.MORNING_BRIEF: "🌅 Morning Brief",
            NotificationPreferences.TASK_REMINDERS: "⏰ Rappels tâches",
        },
        "en": {
            NotificationPreferences.TICKET_REPLIES: "🎧 Ticket replies",
            NotificationPreferences.COMMUNITY_ANNOUNCEMENTS: "📢 Community announcements",
            NotificationPreferences.MORNING_BRIEF: "🌅 Morning Brief",
            NotificationPreferences.TASK_REMINDERS: "⏰ Task reminders",
        },
        "ar": {
            NotificationPreferences.TICKET_REPLIES: "🎧 ردود التذاكر",
            NotificationPreferences.COMMUNITY_ANNOUNCEMENTS: "📢 إعلانات المجتمع",
            NotificationPreferences.MORNING_BRIEF: "🌅 ملخص الصباح",
            NotificationPreferences.TASK_REMINDERS: "⏰ تذكيرات المهام",
        },
    }

    labels = dict(notif_labels.get(lang, notif_labels["fr"]))
    if not get_settings().ENABLE_COMMUNITY:
        labels.pop(NotificationPreferences.COMMUNITY_ANNOUNCEMENTS, None)
    buttons = []
    for notif_type, label in labels.items():
        is_on = notif_type in enabled
        toggle = "✅" if is_on else "❌"
        buttons.append([
            InlineKeyboardButton(
                f"{toggle} {label}",
                callback_data=f"{CB_NOTIF_TOGGLE_PREFIX}{notif_type}",
            )
        ])

    buttons.append([InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_PROFILE)])

    await edit_screen(
        query,
        t("profile.notifications", lang),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def toggle_notification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle une préférence de notification."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    notif_type = query.data.replace(CB_NOTIF_TOGGLE_PREFIX, "")
    db_user: User = context.user_data.get("db_user")

    if db_user:
        if notif_type in db_user.enabled_notifications:
            db_user.enabled_notifications.remove(notif_type)
        else:
            db_user.enabled_notifications.append(notif_type)
        db_user.touch()
        await db_user.save()

    # Réaffiche les notifications avec les toggles à jour
    await show_notifications(update, context)


async def show_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Demande à l'utilisateur de saisir son fuseau horaire."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    current_tz = db_user.timezone if db_user else "UTC"

    tz_labels = {
        "fr": f"🕐 **Fuseau horaire actuel** : {current_tz}\n\nEntrez le nom d'une ville ou un fuseau (ex: Paris, UTC+1, New York) :",
        "en": f"🕐 **Current timezone**: {current_tz}\n\nEnter a city name or timezone (e.g.: Paris, UTC+1, New York):",
        "ar": f"🕐 **المنطقة الزمنية الحالية**: {current_tz}\n\nأدخل اسم مدينة أو منطقة زمنية (مثال: Paris، UTC+1):",
    }

    context.user_data["_awaiting_timezone"] = True

    await edit_screen(
        query,
        tz_labels.get(lang, tz_labels["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.cancel", lang), callback_data=CB_MODULE_PROFILE)]
        ]),
    )


async def handle_timezone_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Traite la saisie du fuseau horaire."""
    if not context.user_data.get("_awaiting_timezone"):
        return

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")
    user_input = update.message.text.strip()

    # Mapping simple ville → fuseau (sera enrichi)
    CITY_TO_TZ = {  # noqa: N806
        "paris": "Europe/Paris", "london": "Europe/London", "londres": "Europe/London",
        "new york": "America/New_York", "los angeles": "America/Los_Angeles",
        "tokyo": "Asia/Tokyo", "dubai": "Asia/Dubai", "dakar": "Africa/Dakar",
        "abidjan": "Africa/Abidjan", "casablanca": "Africa/Casablanca",
        "alger": "Africa/Algiers", "tunis": "Africa/Tunis", "cairo": "Africa/Cairo",
        "le caire": "Africa/Cairo", "riyadh": "Asia/Riyadh", "riyad": "Asia/Riyadh",
        "lagos": "Africa/Lagos", "nairobi": "Africa/Nairobi", "accra": "Africa/Accra",
    }

    tz = CITY_TO_TZ.get(user_input.lower())
    if not tz:
        # Essayer le format UTC±X
        if user_input.upper().startswith("UTC"):
            tz = f"Etc/{user_input.upper().replace(' ', '')}"
        else:
            tz = user_input  # Laisser tel quel, l'utilisateur sait ce qu'il fait

    if db_user:
        db_user.timezone = tz
        db_user.touch()
        await db_user.save()

    context.user_data["_awaiting_timezone"] = False

    confirm = {
        "fr": f"✅ Fuseau horaire mis à jour : **{tz}**",
        "en": f"✅ Timezone updated: **{tz}**",
        "ar": f"✅ تم تحديث المنطقة الزمنية: **{tz}**",
    }

    from src.bot.keyboards import profile_keyboard
    await update.message.reply_text(
        confirm.get(lang, confirm["fr"]),
        reply_markup=profile_keyboard(lang),
    )


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les statistiques de l'utilisateur."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    stats_text = {
        "fr": (
            f"📊 **Mes Statistiques**\n\n"
            f"🎧 Tickets ouverts : **{db_user.total_tickets}**\n"
            f"📅 Membre depuis : **{db_user.created_at.strftime('%d/%m/%Y')}**"
        ),
        "en": (
            f"📊 **My Statistics**\n\n"
            f"🎧 Tickets opened: **{db_user.total_tickets}**\n"
            f"📅 Member since: **{db_user.created_at.strftime('%Y-%m-%d')}**"
        ),
        "ar": (
            f"📊 **إحصائياتي**\n\n"
            f"🎧 التذاكر: **{db_user.total_tickets}**\n"
            f"📅 عضو منذ: **{db_user.created_at.strftime('%Y-%m-%d')}**"
        ),
    }

    await edit_screen(
        query,
        stats_text.get(lang, stats_text["fr"]) + _karma_line(lang, db_user),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_PROFILE)]
        ]),
    )


async def show_morning_brief_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les paramètres du Morning Brief."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    is_enabled = NotificationPreferences.MORNING_BRIEF in db_user.enabled_notifications
    toggle_emoji = "✅" if is_enabled else "❌"
    hour = db_user.morning_brief_hour

    text = {
        "fr": f"🌅 **Morning Brief**\n\nStatut : {toggle_emoji}\nHeure d'envoi : **{hour:02d}:00** ({db_user.timezone})",
        "en": f"🌅 **Morning Brief**\n\nStatus: {toggle_emoji}\nSend time: **{hour:02d}:00** ({db_user.timezone})",
        "ar": f"🌅 **ملخص الصباح**\n\nالحالة: {toggle_emoji}\nوقت الإرسال: **{hour:02d}:00** ({db_user.timezone})",
    }

    toggle_label = {
        "fr": f"{'❌ Désactiver' if is_enabled else '✅ Activer'}",
        "en": f"{'❌ Disable' if is_enabled else '✅ Enable'}",
        "ar": f"{'❌ تعطيل' if is_enabled else '✅ تفعيل'}",
    }

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            toggle_label.get(lang, toggle_label["fr"]),
            callback_data=f"{CB_NOTIF_TOGGLE_PREFIX}{NotificationPreferences.MORNING_BRIEF}",
        )],
        [InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_PROFILE)],
    ])

    await edit_screen(query, text.get(lang, text["fr"]), reply_markup=keyboard)


def register_profile_handlers(application) -> None:
    """Enregistre les handlers du profil utilisateur."""
    # Affichage profil
    application.add_handler(CallbackQueryHandler(show_profile, pattern=f"^{CB_MODULE_PROFILE}$"))

    # Changement de langue depuis le profil
    application.add_handler(CallbackQueryHandler(change_language, pattern=f"^{CB_PROFILE_CHANGE_LANG}$"))
    application.add_handler(CallbackQueryHandler(language_changed_from_profile, pattern=r"^profile_lang:(fr|en|ar)$"))

    # Notifications
    application.add_handler(CallbackQueryHandler(show_notifications, pattern=f"^{CB_PROFILE_NOTIFICATIONS}$"))
    application.add_handler(CallbackQueryHandler(toggle_notification, pattern=f"^{CB_NOTIF_TOGGLE_PREFIX}"))

    # Fuseau horaire
    application.add_handler(CallbackQueryHandler(show_timezone, pattern=f"^{CB_PROFILE_TIMEZONE}$"))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_timezone_input),
        group=5,  # Group séparé pour ne pas interférer
    )

    # Statistiques
    application.add_handler(CallbackQueryHandler(show_stats, pattern=f"^{CB_PROFILE_STATS}$"))

    # Morning Brief
    application.add_handler(CallbackQueryHandler(show_morning_brief_settings, pattern=f"^{CB_PROFILE_MORNING_BRIEF}$"))

    logger.info("Handlers profil enregistrés")
