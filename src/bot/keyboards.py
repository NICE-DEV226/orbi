"""
Orbi — Constantes de callback_data et constructeurs de claviers inline.
Point centralisé pour éviter les chaînes magiques dans les handlers.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.core.i18n import t

# ─────────────────────────────────────
# Callback Data Constants
# ─────────────────────────────────────

# Navigation
CB_HOME = "nav:home"
CB_BACK = "nav:back"

# Sélection de langue
CB_LANG_FR = "lang:fr"
CB_LANG_EN = "lang:en"
CB_LANG_AR = "lang:ar"

# Menu principal — Modules
CB_MODULE_SUPPORT = "mod:support"
CB_MODULE_SHOP = "mod:shop"
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


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Clavier du menu principal avec les 5 modules + profil."""
    return InlineKeyboardMarkup([
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
    ])


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
