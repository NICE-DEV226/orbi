"""
Commandes utilitaires pour ajouter le bot à des groupes et canaux.
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes

from src.core.i18n import t

logger = logging.getLogger("orbi.handlers.group_utils")


async def add_to_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explique comment ajouter le bot à un groupe."""
    if not update.message:
        return
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Guide Telegram", url="https://core.telegram.org/bots#adding-a-bot-to-a-group"),
            InlineKeyboardButton("🔧 Configuration", callback_data="group:config"),
        ],
        [
            InlineKeyboardButton("📋 Règles du groupe", callback_data="group:rules"),
            InlineKeyboardButton("🛡️ Modération", callback_data="group:moderation"),
        ],
        [
            InlineKeyboardButton("❌ Retour", callback_data="nav:home"),
        ]
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
        [
            InlineKeyboardButton("📖 Guide Canal", url="https://core.telegram.org/bots#adding-a-bot-to-a-channel"),
            InlineKeyboardButton("📢 Configuration", callback_data="channel:config"),
        ],
        [
            InlineKeyboardButton("📊 Statistiques", callback_data="channel:stats"),
            InlineKeyboardButton("❌ Retour", callback_data="nav:home"),
        ]
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


async def group_config_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback pour la configuration de groupe."""
    if update.callback_query:
        await update.callback_query.answer()
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👋 Bienvenue", callback_data="group:welcome"),
            InlineKeyboardButton("📋 Règles", callback_data="group:rules"),
        ],
        [
            InlineKeyboardButton("🛡️ Modération", callback_data="group:moderation"),
            InlineKeyboardButton("📊 Stats", callback_data="group:stats"),
        ],
        [
            InlineKeyboardButton("❌ Retour", callback_data="group:main"),
        ]
    ])
    
    text = """
🔧 **Configuration du Groupe**

👋 **Messages de bienvenue**
• Personnaliser le message de bienvenue
• Mentionner les règles automatiquement
• Boutons d'action rapide

📋 **Système de règles**
• Définir les règles du groupe
• Affichage automatique aux nouveaux
• Sanctions progressives

🛡️ **Modération automatique**
• Anti-spam intelligent
• Anti-flood (limite de messages)
• Filtre de liens suspects
• Sanctions automatiques

📊 **Monitoring**
• Messages par jour
• Utilisateurs actifs
• Actions de modération

---

**Configurez chaque option ci-dessous !**
    """
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


def register_group_utils_handlers(application) -> None:
    """Enregistre les handlers utilitaires pour groupes."""
    
    # Commandes
    application.add_handler(CommandHandler("addgroup", add_to_group_command))
    application.add_handler(CommandHandler("addchannel", add_to_channel_command))
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(group_config_callback, pattern=r"^group:config$"))
    
    # Handlers temporaires pour les callbacks
    application.add_handler(CallbackQueryHandler(
        lambda u, c: c.bot.send_message(
            chat_id=u.effective_chat.id,
            text="👋 **Messages de bienvenue**\n\n⚙️ Fonctionnalité disponible une fois le bot ajouté au groupe",
            parse_mode="HTML"
        ), 
        pattern=r"^group:(welcome|rules|moderation|stats|main)$"
    ))
    
    application.add_handler(CallbackQueryHandler(
        lambda u, c: c.bot.send_message(
            chat_id=u.effective_chat.id,
            text="📢 **Configuration du canal**\n\n⚙️ Fonctionnalité disponible une fois le bot ajouté au canal",
            parse_mode="HTML"
        ), 
        pattern=r"^channel:(config|stats)$"
    ))
    
    logger.info("Handlers utilitaires de groupe enregistrés")
