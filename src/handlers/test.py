"""
Test simple pour vérifier si le bot répond aux commandes.
"""

import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

logger = logging.getLogger("orbi.handlers.test")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande de test simple."""
    if not update.message:
        return
    
    await update.message.reply_text("✅ Bot fonctionne !")


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande ping pour tester la latence."""
    if not update.message:
        return
    
    await update.message.reply_text("🏓 Pong !")


def register_test_handlers(application) -> None:
    """Enregistre les handlers de test."""
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CommandHandler("ping", ping_command))
    
    logger.info("Handlers de test enregistrés")
