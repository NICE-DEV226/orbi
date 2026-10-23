"""
Orbi — Commandes Utilitaires pour Démo.
Commandes pour ajouter le bot à un groupe et voir les fonctionnalités.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

logger = logging.getLogger("orbi.handlers.utils")


async def add_to_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explique comment ajouter le bot à un groupe."""
    if not update.message:
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Guide Complet", url="https://core.telegram.org/bots#adding-a-bot-to-a-group"),
            InlineKeyboardButton("🤖 Tester maintenant", callback_data="demo:group_test"),
        ],
        [
            InlineKeyboardButton("🔧 Configuration Groupe", callback_data="demo:group_config"),
            InlineKeyboardButton("📋 Fonctionnalités", callback_data="demo:group_features"),
        ]
    ])

    text = """
👥 **Comment ajouter Orbi à un groupe**

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

🔧 **Testez maintenant :**
Ajoutez le bot à un groupe et testez les commandes `/config` et `/rules`
    """

    await update.message.reply_text(text, reply_markup=keyboard)


async def demo_group_features(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Montre les fonctionnalités de groupe - VERSION RAPIDE."""
    if update.callback_query:
        await update.callback_query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ Anti-Spam", callback_data="demo:antispam")],
        [InlineKeyboardButton("👋 Bienvenue", callback_data="demo:welcome")],
        [InlineKeyboardButton("📋 Règles", callback_data="demo:rules")],
        [InlineKeyboardButton("📊 Stats", callback_data="demo:stats")],
        [InlineKeyboardButton("❌ Retour", callback_data="demo:main")]
    ])

    text = """
👥 **Fonctionnalités de Groupe**

🛡️ **Modération Automatique**
• Anti-spam & anti-flood
• Filtre de liens suspects
• Sanctions automatiques

👋 **Messages de Bienvenue**
• Personnalisables
• Mention des règles

📋 **Système de Règles**
• Règles personnalisables
• Sanctions progressives

📊 **Monitoring & Stats**
• Messages par jour
• Utilisateurs actifs

**Ajoutez le bot à un groupe pour tester !**
    """

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


async def demo_dev_features(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Montre les fonctionnalités développeur réelles - VERSION RAPIDE."""
    if update.callback_query:
        await update.callback_query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Créer API Key", callback_data="dev:create_api_key")],
        [InlineKeyboardButton("🔗 Configurer Webhook", callback_data="dev:webhooks")],
        [InlineKeyboardButton("📊 Voir les Logs", callback_data="dev:api_logs")],
        [InlineKeyboardButton("📈 Performance", callback_data="dev:performance")],
        [InlineKeyboardButton("📖 Documentation", url="http://localhost:8000/docs")],
        [InlineKeyboardButton("❌ Retour", callback_data="demo:main")]
    ])

    text = """
👨‍💻 **Fonctionnalités Développeur**

🔑 **API Keys Management**
• Clés sécurisées avec scopes
• Rate limiting par clé
• Logs d'utilisation

🔗 **Webhooks System**
• Configuration d'URLs
• Événements en temps réel
• Retry automatique

📊 **Monitoring & Logs**
• Logs API temps réel
• Métriques de performance
• Error tracking

📈 **Performance Dashboard**
• Uptime et latence
• Requêtes par minute
• Memory usage

📖 **Documentation Interactive**
• Swagger UI : `/docs`
• ReDoc : `/redoc`
• Testeur d'API

**Accédez à http://localhost:8000/docs**
    """

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


async def demo_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menu principal de démonstration - VERSION RAPIDE."""
    if update.callback_query:
        await update.callback_query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Ajouter à un Groupe", callback_data="demo:group_add")],
        [InlineKeyboardButton("👨‍💻 Fonctions Développeur", callback_data="demo:dev_features")],
        [InlineKeyboardButton("🔧 Admin Dashboard", callback_data="admin:panel")],
        [InlineKeyboardButton("📊 API Documentation", url="http://localhost:8000/docs")],
        [InlineKeyboardButton("❌ Fermer", callback_data="demo:close")]
    ])

    text = """
🚀 **Menu Démonstration Orbi**

👥 **Gestion de Groupe**
• Modération automatique
• Messages de bienvenue
• Système de règles

👨‍💻 **Fonctionnalités Développeur**
• API Keys management
• Webhooks system
• Monitoring temps réel

🔧 **Admin Dashboard**
• Magic Links sécurisés
• Statistiques détaillées

📊 **API REST**
• Endpoints complets
• Documentation Swagger

**Testez chaque fonctionnalité !**
    """

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


def register_demo_handlers(application) -> None:
    """Enregistre les handlers de démonstration."""

    # Commandes
    application.add_handler(CommandHandler("addgroup", add_to_group_command))
    application.add_handler(CommandHandler("demo", lambda u, c: demo_main_menu(u, c)))

    # Callbacks
    application.add_handler(CallbackQueryHandler(demo_main_menu, pattern=r"^demo:main$"))
    application.add_handler(CallbackQueryHandler(demo_group_features, pattern=r"^demo:group_features$"))
    application.add_handler(CallbackQueryHandler(demo_dev_features, pattern=r"^demo:dev_features$"))
    application.add_handler(CallbackQueryHandler(add_to_group_command, pattern=r"^demo:group_add$"))

    # Handlers temporaires pour les callbacks non implémentés
    application.add_handler(CallbackQueryHandler(
        lambda u, c: c.bot.send_message(
            chat_id=u.effective_chat.id,
            text="🔧 Fonctionnalité en développement - Utilisez le menu principal pour tester"
        ),
        pattern=r"^demo:(group_test|group_config|antispam|welcome|rules|stats|config|close)$"
    ))

    logger.info("Handlers de démonstration enregistrés")
