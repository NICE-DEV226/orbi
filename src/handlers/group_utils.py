"""
Commandes utilitaires pour ajouter le bot à des groupes et canaux.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes

logger = logging.getLogger("orbi.handlers.group_utils")


async def add_to_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explique comment ajouter le bot à un groupe."""
    if not update.message:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Guide Telegram", url="https://core.telegram.org/bots#adding-a-bot-to-a-group")],
        [InlineKeyboardButton("❌ Retour", callback_data="nav:home")],
    ])

    text = """
👥 **Ajouter Orbi à un groupe**

📋 **Étapes simples :**

1️⃣ **Ouvrez votre groupe Telegram**
2️⃣ **Cliquez sur le nom du groupe** → "Membres" → "Ajouter des membres"
3️⃣ **Cherchez @votre_bot_orbi** (remplacez par votre nom de bot)
4️⃣ **Ajoutez le bot** et **promouvez-le en admin**

⚙️ **Permissions requises :**
• ✅ Envoyer des messages
• ✅ Supprimer des messages (modération)
• ✅ Bannir des utilisateurs (modération)
• ✅ Ajouter des admins (configuration)

🚀 **Fonctionnalités une fois ajouté :**
• 🎯 **Modération automatique** (anti-spam, anti-flood)
• 👋 **Messages de bienvenue** personnalisés
• 📋 **Règles du groupe** avec sanctions
• 📊 **Statistiques** et monitoring
• 🔧 **Configuration** via le bot

---

**Commandes disponibles dans le groupe :**
• `/config` - Configuration du groupe
• `/rules` - Afficher les règles
• `/admin` - Menu admin
• `/stats` - Statistiques du groupe
    """

    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


async def add_to_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explique comment ajouter le bot à un canal."""
    if not update.message:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Guide Canal", url="https://core.telegram.org/bots#adding-a-bot-to-a-channel")],
        [InlineKeyboardButton("❌ Retour", callback_data="nav:home")],
    ])

    text = """
📢 **Ajouter Orbi à un canal**

📋 **Étapes simples :**

1️⃣ **Ouvrez votre canal Telegram**
2️⃣ **Cliquez sur le nom du canal** → "Administrateurs" → "Ajouter un admin"
3️⃣ **Cherchez @votre_bot_orbi** (remplacez par votre nom de bot)
4️⃣ **Ajoutez le bot** avec les permissions

⚙️ **Permissions requises :**
• ✅ Envoyer des messages
• ✅ Modifier les messages
• ✅ Supprimer les messages
• ✅ Inviter des utilisateurs

🚀 **Fonctionnalités dans le canal :**
• 📢 **Publication automatique**
• 📊 **Statistiques de vues**
• 📝 **Modération des commentaires**
• 🎯 **Programmation de messages**
• 📈 **Analyse de performance**

---

**Commandes disponibles dans le canal :**
• `/config` - Configuration du canal
• `/stats` - Statistiques du canal
• `/post` - Publier un message
• `/schedule` - Programmer une publication
    """

    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


def register_group_utils_handlers(application) -> None:
    """Enregistre les handlers utilitaires pour groupes."""

    # Commandes
    application.add_handler(CommandHandler("addgroup", add_to_group_command))
    application.add_handler(CommandHandler("addchannel", add_to_channel_command))

    logger.info("Handlers utilitaires de groupe enregistrés")
