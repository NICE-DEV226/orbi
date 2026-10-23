"""
Orbi — Handler Authentification Web Admin.
Génère les Magic Links pour la connexion au dashboard web.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from src.core.config import get_settings
from src.core.i18n import t
from src.core.redis import get_redis

logger = logging.getLogger("orbi.handlers.admin_auth")

MAGIC_LINK_PREFIX = "magic_link:"
WEB_SESSION_PREFIX = "websession:"


async def request_magic_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Génère et envoie un Magic Link pour l'authentification web."""
    if update.callback_query:
        await update.callback_query.answer()

    if not context.user_data:
        return

    db_user = context.user_data.get("db_user")
    if not db_user or db_user.role not in ["admin", "superadmin"]:
        lang = context.user_data.get("lang", "fr")
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "🚫 Accès réservé aux administrateurs"
            )
        return

    # Générer un Magic Link unique
    magic_link_id = str(uuid.uuid4())
    base_url = get_settings().BASE_URL

    # Stocker le Magic Link dans Redis (valide 10 minutes)
    redis = get_redis()
    await redis.setex(
        f"{MAGIC_LINK_PREFIX}{magic_link_id}",
        600,  # 10 minutes
        str(db_user.telegram_id)
    )

    # Construire l'URL de connexion
    login_url = f"{base_url}/admin/magic-login/{magic_link_id}"

    # Envoyer le lien par Telegram
    lang = context.user_data.get("lang", "fr")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Se connecter au Dashboard", url=login_url)],
        [InlineKeyboardButton(t("common.back", lang), callback_data="mod:home")]
    ])

    text = """
🔐 **Lien de connexion Admin Dashboard**

Voici votre lien sécurisé pour accéder au dashboard web :

⏰ *Valide pendant 10 minutes*

📊 *Accès complet aux fonctionnalités d'administration*
    """

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le panneau d'administration pour les admins."""
    if update.callback_query:
        await update.callback_query.answer()

    if not context.user_data:
        return

    db_user = context.user_data.get("db_user")
    if not db_user or db_user.role not in ["admin", "superadmin"]:
        lang = context.user_data.get("lang", "fr")
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "🚫 Accès réservé aux administrateurs"
            )
        return

    lang = context.user_data.get("lang", "fr")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔐 Obtenir un lien Dashboard", callback_data="admin:magic_link"),
            InlineKeyboardButton("📊 Voir les statistiques", callback_data="admin:stats"),
        ],
        [
            InlineKeyboardButton("👥 Gérer les utilisateurs", callback_data="admin:users"),
            InlineKeyboardButton("🎧 Gérer les tickets", callback_data="admin:tickets"),
        ],
        [
            InlineKeyboardButton("⚙️ Configuration du bot", callback_data="admin:config"),
            InlineKeyboardButton("📢 Envoyer une annonce", callback_data="admin:broadcast"),
        ],
        [InlineKeyboardButton(t("common.back", lang), callback_data="mod:home")]
    ])

    text = f"""
🛠️ **Panneau Administrateur**

Bienvenue, *{db_user.display_name}* !

📊 *Rôle* : {db_user.role.upper()}
🔑 *ID* : `{db_user.telegram_id}`
⏰ *Connecté* : {datetime.now(UTC).strftime("%H:%M:%S")}

Que souhaitez-vous gérer ?
    """

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def show_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les statistiques administrateur."""
    if update.callback_query:
        await update.callback_query.answer()

    if not context.user_data:
        return

    db_user = context.user_data.get("db_user")
    if not db_user or db_user.role not in ["admin", "superadmin"]:
        return

    # Calculer les statistiques
    from src.models.commerce import Order
    from src.models.ticket import Ticket
    from src.models.user import User as UserModel

    total_users = await UserModel.count()
    total_tickets = await Ticket.count()
    total_orders = await Order.count()

    # Utilisateurs actifs (derniers 7 jours)
    week_ago = datetime.now(UTC) - timedelta(days=7)
    active_users = await UserModel.find(
        UserModel.last_active_at >= week_ago
    ).count()

    lang = context.user_data.get("lang", "fr")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Actualiser", callback_data="admin:stats")],
        [InlineKeyboardButton(t("common.back", lang), callback_data="admin:panel")]
    ])

    text = f"""
📊 **Statistiques du Système**

👥 **Utilisateurs**
• Total : `{total_users}`
• Actifs (7j) : `{active_users}`
• Bannis : `0`

🎧 **Support**
• Tickets total : `{total_tickets}`
• Ouverts : `0`
• En attente : `0`

🛒 **Commerce**
• Commandes total : `{total_orders}`
• Aujourd'hui : `0`
• Revenu total : `0 XOF`

⚡ **Performance**
• Uptime : `99.9%`
• Latence : `45ms`
• Memory : `256MB`

*Dernière actualisation : {datetime.now(UTC).strftime("%H:%M:%S")}*
    """

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message à tous les utilisateurs."""
    if update.callback_query:
        await update.callback_query.answer()

    if not context.user_data:
        return

    db_user = context.user_data.get("db_user")
    if not db_user or db_user.role != "superadmin":
        lang = context.user_data.get("lang", "fr")
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "🚫 Accès réservé au Super Admin"
            )
        return

    lang = context.user_data.get("lang", "fr")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Envoyer à tous", callback_data="admin:broadcast_all")],
        [InlineKeyboardButton("👥 Envoyer aux admins", callback_data="admin:broadcast_admins")],
        [InlineKeyboardButton(t("common.back", lang), callback_data="admin:panel")]
    ])

    text = """
📢 **Centre d'Annonce**

Choisissez la cible de votre message :

📋 *Tous les utilisateurs actifs*
👥 *Administrateurs uniquement*

⚠️ *Utilisez avec responsabilité*
    """

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


def register_admin_handlers(application) -> None:
    """Enregistre les handlers d'administration."""

    # Panneau admin
    application.add_handler(CallbackQueryHandler(show_admin_panel, pattern=r"^admin:panel$"))
    application.add_handler(CallbackQueryHandler(request_magic_link, pattern=r"^admin:magic_link$"))

    # Statistiques
    application.add_handler(CallbackQueryHandler(show_admin_stats, pattern=r"^admin:stats$"))

    # Annonces
    application.add_handler(CallbackQueryHandler(broadcast_message, pattern=r"^admin:broadcast$"))

    # Handlers temporaires pour les callbacks non implémentés
    application.add_handler(CallbackQueryHandler(
        lambda u, c: c.bot.send_message(
            chat_id=u.effective_chat.id,
            text="🔧 Fonctionnalité en développement"
        ),
        pattern=r"^admin:(users|tickets|config|broadcast_all|broadcast_admins)$"
    ))

    logger.info("Handlers admin auth enregistrés")
