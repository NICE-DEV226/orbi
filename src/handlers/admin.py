"""
Orbi — Commande Magic Link pour accès Admin (Phase 10).
Permet de générer un lien auto-connecté valable 5 minutes.
"""

import logging
import uuid
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from src.core.config import get_settings
from src.core.redis import get_redis
from src.web.auth import MAGIC_LINK_PREFIX

logger = logging.getLogger("orbi.handlers.admin")

async def generate_magic_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Génère un lien unique pour accéder au Dashboard d'Administration Web."""
    user = context.user_data.get("db_user")
    
    if not user or user.role not in ["admin", "superadmin"]:
        await update.message.reply_text("⛔ Rôle administrateur requis.")
        return

    # Génération Token
    token = str(uuid.uuid4())
    redis = get_redis()
    
    # 300 secondes = 5 minutes
    await redis.setex(f"{MAGIC_LINK_PREFIX}{token}", 300, str(user.telegram_id))
    
    # Lien de base
    base_url = get_settings().BASE_URL
    magic_url = f"{base_url}/admin/auth/{token}"

    text = (
        "🔐 **Lien d'Accès Administration**\n\n"
        "Votre Magic Link ci-dessous vous permet de vous connecter au Dashboard Web Orbi "
        "en toute sécurité sans mot de passe.\n\n"
        f"👉 [Accéder au Dashboard]({magic_url})\n\n"
        "⏳ _Ce lien expirera dans 5 minutes et ne servira qu'une seule fois._"
    )

    await update.message.reply_text(text, parse_mode="Markdown")

def register_admin_handlers(application) -> None:
    """Enregistre la commande /web pour les administrateurs."""
    application.add_handler(CommandHandler("web", generate_magic_link))
    logger.info("Commande /web enregistrée")
