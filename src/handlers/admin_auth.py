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
from src.core.text import esc

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
    login_url = f"{base_url}/admin/auth/{magic_link_id}"

    # Envoyer le lien par Telegram
    lang = context.user_data.get("lang", "fr")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Se connecter au Dashboard", url=login_url)],
        [InlineKeyboardButton(t("common.back", lang), callback_data="nav:home")]
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
        [InlineKeyboardButton(t("common.back", lang), callback_data="nav:home")]
    ])

    text = f"""
🛠️ **Panneau Administrateur**

Bienvenue, *{esc(db_user.display_name)}* !

📊 *Rôle* : {db_user.role.upper()}
🔑 *ID* : `{db_user.telegram_id}`
⏰ *Connecté* : {datetime.now(UTC).strftime("%H:%M:%S")}

Que souhaitez-vous faire ?
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

    # Statistiques réelles (aucune valeur inventée)
    from src.models.ticket import Ticket
    from src.models.user import User as UserModel
    from src.orbi_dev.models import Execution
    from src.orbi_dev.state import ACTIVE_STATUSES

    total_users = await UserModel.count()
    banned_users = await UserModel.find(UserModel.is_banned == True).count()  # noqa: E712
    week_ago = datetime.now(UTC) - timedelta(days=7)
    active_users = await UserModel.find(UserModel.last_active_at >= week_ago).count()
    total_tickets = await Ticket.count()
    open_tickets = await Ticket.find({"status": {"$in": ["open", "in_progress"]}}).count()
    active_executions = await Execution.find({"status": {"$in": [st.value for st in ACTIVE_STATUSES]}}).count()
    pull_requests = await Execution.find({"pr_url": {"$ne": None}}).count()

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
• Bannis : `{banned_users}`

🎧 **Support**
• Tickets total : `{total_tickets}`
• Ouverts : `{open_tickets}`

🤖 **Orbi Dev**
• Exécutions en cours : `{active_executions}`
• Pull requests proposées : `{pull_requests}`

*Dernière actualisation : {datetime.now(UTC).strftime("%H:%M:%S")}*
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

    logger.info("Handlers admin auth enregistrés")
