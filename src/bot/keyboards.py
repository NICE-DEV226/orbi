"""
Orbi — Constantes de callback_data et constructeurs de claviers inline.
Point centralisé pour éviter les chaînes magiques dans les handlers.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from src.core.config import get_settings
from src.core.i18n import t

# ─────────────────────────────────────
# Callback Data Constants
# ─────────────────────────────────────

# Navigation
CB_HOME = "nav:home"
CB_BACK = "nav:back"
CB_MORE = "nav:more"  # administrateurs : les autres modules, derrière l'accueil Orbi Dev
CB_DEV_HOME = "dv:home"

# Sélection de langue
CB_LANG_FR = "lang:fr"
CB_LANG_EN = "lang:en"
CB_LANG_AR = "lang:ar"

# Menu principal — Modules
CB_MODULE_SUPPORT = "mod:support"
CB_MODULE_COMMUNITY = "mod:community"
CB_MODULE_PRODUCTIVITY = "mod:productivity"
CB_MODULE_DEVELOPERS = "mod:developers"
CB_MODULE_PROFILE = "mod:profile"

# Profil
CB_PROFILE_CHANGE_LANG = "profile:change_lang"
CB_PROFILE_NOTIFICATIONS = "profile:notifications"
CB_PROFILE_TIMEZONE = "profile:timezone"
CB_PROFILE_STATS = "profile:stats"
CB_PROFILE_MORNING_BRIEF = "profile:morning_brief"

# Notifications toggle
CB_NOTIF_TOGGLE_PREFIX = "notif:toggle:"  # + type de notification
CB_NOTIF_SAVE = "notif:save"


# ─────────────────────────────────────
# Constructeurs de Claviers
# ─────────────────────────────────────

def language_selector_keyboard() -> InlineKeyboardMarkup:
    """Clavier de sélection de langue (affiché au premier contact)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇫🇷 Français", callback_data=CB_LANG_FR),
            InlineKeyboardButton("🇬🇧 English", callback_data=CB_LANG_EN),
            InlineKeyboardButton("🇸🇦 العربية", callback_data=CB_LANG_AR),
        ]
    ])


def orbi_dev_button(label: str = "🤖 Orbi Dev") -> InlineKeyboardButton | None:
    """Bouton qui ouvre Orbi Dev comme Mini App Telegram. Telegram exige une URL https publique : sinon, pas de bouton."""
    settings = get_settings()
    if not settings.public_https:
        return None
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=f"{settings.BASE_URL.rstrip('/')}/dev/"))


def main_menu_keyboard(lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """
    Clavier du menu principal. Le module Communauté n'apparaît que s'il est activé (ENABLE_COMMUNITY) ;
    Orbi Dev et l'administration n'apparaissent que pour les administrateurs.
    """
    support = InlineKeyboardButton(t("menu.main.support", lang), callback_data=CB_MODULE_SUPPORT)
    productivity = InlineKeyboardButton(t("menu.main.productivity", lang), callback_data=CB_MODULE_PRODUCTIVITY)
    developers = InlineKeyboardButton(t("menu.main.developers", lang), callback_data=CB_MODULE_DEVELOPERS)
    profile = InlineKeyboardButton(t("menu.main.profile", lang), callback_data=CB_MODULE_PROFILE)

    if get_settings().ENABLE_COMMUNITY:
        community = InlineKeyboardButton(t("menu.main.community", lang), callback_data=CB_MODULE_COMMUNITY)
        rows = [
            [support, community],
            [productivity, developers],
            [profile],
            [
                InlineKeyboardButton("👥 Ajouter à un groupe", callback_data="group:add"),
                InlineKeyboardButton("📢 Ajouter à un canal", callback_data="channel:add"),
            ],
        ]
    else:
        rows = [[support, productivity], [developers], [profile]]

    if is_admin:
        rows.insert(0, [
            InlineKeyboardButton("‹ Orbi Dev", callback_data=CB_DEV_HOME),
            InlineKeyboardButton("🔐 Administration", callback_data="admin:panel"),
        ])
    return InlineKeyboardMarkup(rows)


def profile_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Clavier de la page profil."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("profile.change_language", lang), callback_data=CB_PROFILE_CHANGE_LANG),
            InlineKeyboardButton(t("profile.notifications", lang), callback_data=CB_PROFILE_NOTIFICATIONS),
        ],
        [
            InlineKeyboardButton(t("profile.timezone", lang), callback_data=CB_PROFILE_TIMEZONE),
            InlineKeyboardButton(t("profile.stats", lang), callback_data=CB_PROFILE_STATS),
        ],
        [
            InlineKeyboardButton(t("profile.morning_brief", lang), callback_data=CB_PROFILE_MORNING_BRIEF),
        ],
        [
            InlineKeyboardButton(t("common.back", lang), callback_data=CB_HOME),
        ],
    ])


def back_to_home_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Clavier simple avec bouton retour au menu principal."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)]
    ])


def confirm_cancel_keyboard(
    lang: str,
    confirm_callback: str,
    cancel_callback: str = CB_HOME,
) -> InlineKeyboardMarkup:
    """Clavier Confirmer / Annuler générique."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("common.confirm", lang), callback_data=confirm_callback),
            InlineKeyboardButton(t("common.cancel", lang), callback_data=cancel_callback),
        ]
    ])
