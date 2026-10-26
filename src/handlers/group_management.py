"""
Orbi — Handlers Groupes et Canaux.
Gestion des bots dans les groupes, modération, règles, et administration.
"""

import logging
from datetime import UTC, datetime, timedelta

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ChatMemberHandler, ContextTypes, MessageHandler, filters

from src.core.text import esc
from src.models.community import GroupConfig, ModerationAction, ModerationLog

logger = logging.getLogger("orbi.handlers.group")


async def handle_new_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère l'arrivée du bot dans un nouveau groupe."""
    if not update.my_chat_member:
        return

    new_status = update.my_chat_member.new_chat_member.status

    # Le bot a été ajouté au groupe
    if new_status in ["member", "administrator"]:
        await handle_bot_added_to_group(update, context)
    # Le bot a été retiré du groupe
    elif new_status in ["left", "kicked"]:
        await handle_bot_removed_from_group(update, context)


async def handle_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configure le bot lorsqu'il est ajouté à un groupe."""
    chat = update.effective_chat

    # Créer ou récupérer la configuration du groupe
    group_config = await GroupConfig.find_one(GroupConfig.chat_id == chat.id)

    if not group_config:
        group_config = GroupConfig(
            chat_id=chat.id,
            chat_title=chat.title,
            auto_moderation_enabled=True,
            welcome_message_template=(
                "👋 Bienvenue {name} dans {group} !\n\n"
                "📋 Veuillez respecter les règles :\n"
                "• Pas de spam\n"
                "• Pas de liens sans autorisation\n"
                "• Respect mutuel\n\n"
                "Bon séjour ! 🎉"
            ),
            rules_text=(
                "📋 **Règles du groupe**\n\n"
                "1️⃣ Respect mutuel obligatoire\n"
                "2️⃣ Pas de spam publicitaire\n"
                "3️⃣ Pas de contenu inapproprié\n"
                "4️⃣ Pas de liens suspects\n"
                "5️⃣ Écouter les administrateurs\n\n"
                "⚠️ Le non-respect entraînera un mute/ban"
            )
        )
        await group_config.insert()
        logger.info(f"Nouvelle configuration créée pour le groupe {chat.title} ({chat.id})")

    # Envoyer le message de bienvenue et configuration
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚙️ Configuration", callback_data=f"group:config:{chat.id}"),
            InlineKeyboardButton("📋 Règles", callback_data=f"group:rules:{chat.id}"),
        ],
    ])

    await context.bot.send_message(
        chat_id=chat.id,
        text="""
🤖 **Orbi Bot configuré !**

Je suis maintenant actif dans ce groupe. Voici ce que je peux faire :

🔹 **Modération automatique** (anti-spam, anti-flood)
🔹 **Messages de bienvenue** personnalisés  
🔹 **Système de règles** et sanctions
🔹 **Statistiques** du groupe
🔹 **Sondages** interactifs

Cliquez sur les boutons ci-dessous pour configurer le bot selon vos besoins !
        """,
        reply_markup=keyboard
    )


async def handle_bot_removed_from_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Nettoie la configuration lorsque le bot est retiré."""
    chat = update.effective_chat

    # Marquer le groupe comme inactif
    group_config = await GroupConfig.find_one(GroupConfig.chat_id == chat.id)
    if group_config:
        group_config.auto_moderation_enabled = False
        await group_config.save()
        logger.info(f"Bot retiré du groupe {chat.title} ({chat.id}) - Modération désactivée")


async def show_group_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le panneau de configuration du groupe."""
    if update.callback_query:
        await update.callback_query.answer()

    # Extraire le chat_id du callback_data
    callback_data = update.callback_query.data
    chat_id = int(callback_data.split(":")[-1]) if ":" in callback_data else update.effective_chat.id

    group_config = await GroupConfig.find_one(GroupConfig.chat_id == chat_id)
    if not group_config:
        await update.effective_message.reply_text("❌ Configuration non trouvée")
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Règles du groupe", callback_data=f"group:rules:{chat_id}"),
            InlineKeyboardButton("🔧 Modération auto", callback_data=f"group:auto_mod:{chat_id}"),
        ],
        [InlineKeyboardButton("❌ Retour", callback_data="nav:home")],
    ])

    status = "✅ Activé" if group_config.auto_moderation_enabled else "❌ Désactivé"

    text = f"""
⚙️ **Configuration du Groupe**

📛 *Nom* : {esc(group_config.chat_title)}
🆔 *ID* : `{chat_id}`
🔧 *Modération auto* : {status}

Que souhaitez-vous configurer ?
    """

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def toggle_auto_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Active/désactive la modération automatique."""
    if update.callback_query:
        await update.callback_query.answer()

    callback_data = update.callback_query.data
    chat_id = int(callback_data.split(":")[-1])

    group_config = await GroupConfig.find_one(GroupConfig.chat_id == chat_id)
    if not group_config:
        return

    group_config.auto_moderation_enabled = not group_config.auto_moderation_enabled
    await group_config.save()

    status = "activée" if group_config.auto_moderation_enabled else "désactivée"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Retour à la config", callback_data=f"group:config:{chat_id}")],
        [InlineKeyboardButton("❌ Retour au menu", callback_data="nav:home")]
    ])

    text = f"""
🔧 **Modération Automatique**

La modération automatique est maintenant **{status}**.

📋 **Fonctions activées :**
• Anti-spam (détection de messages répétitifs)
• Anti-flood (limite de messages par minute)  
• Filtre de liens suspects
• Filtre de mentions excessives

*Les administrateurs ne sont pas affectés par ces règles.*
    """

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def show_group_rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les règles du groupe."""
    if update.callback_query:
        await update.callback_query.answer()

    callback_data = update.callback_query.data
    chat_id = int(callback_data.split(":")[-1])

    group_config = await GroupConfig.find_one(GroupConfig.chat_id == chat_id)
    if not group_config:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Retour à la config", callback_data=f"group:config:{chat_id}")],
    ])

    text = f"""
📋 **Règles du Groupe**

{esc(group_config.rules_text) if group_config.rules_text else "Aucune règle définie"}

*Les règles sont visibles par tous les membres du groupe.*
    """

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def handle_message_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Effectue la modération automatique des messages."""
    if not update.message or not update.effective_chat:
        return

    chat = update.effective_chat
    message = update.message
    user = message.from_user

    # Ne pas modérer les messages des admins
    if user and user.username in ["GroupAdmin", "GroupCreator"]:  # À adapter
        return

    group_config = await GroupConfig.find_one(GroupConfig.chat_id == chat.id)
    if not group_config or not group_config.auto_moderation_enabled:
        return

    # Récupérer le statut de l'utilisateur dans le groupe
    try:
        chat_member = await context.bot.get_chat_member(chat.id, user.id)
        if chat_member.status in ["administrator", "creator"]:
            return
    except Exception:
        pass

    # Détection de spam/flood
    spam_detected = False
    reason = ""

    # 1. Messages identiques répétés
    if message.text:
        recent_messages = await context.bot.get_chat_history(chat.id, limit=10)
        identical_count = sum(1 for msg in recent_messages if msg.text == message.text)

        if identical_count >= group_config.max_identical_messages:
            spam_detected = True
            reason = "Messages identiques répétés"

    # 2. Trop de mentions
    if message.entities:
        mention_count = sum(1 for entity in message.entities if entity.type == "mention")
        if mention_count > group_config.max_mentions_per_message:
            spam_detected = True
            reason = "Trop de mentions"

    # 3. Liens suspects (si non autorisés)
    if not group_config.allow_links and message.entities:
        link_count = sum(1 for entity in message.entities if entity.type in ["url", "text_link"])
        if link_count > 0:
            spam_detected = True
            reason = "Liens non autorisés"

    # Appliquer la sanction
    if spam_detected:
        await apply_spam_punishment(update, context, user.id, reason, group_config)


async def apply_spam_punishment(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, reason: str, group_config: GroupConfig) -> None:
    """Applique une sanction pour spam."""
    chat = update.effective_chat

    # Logger l'action
    await ModerationLog(
        target_telegram_id=user_id,
        target_username=update.message.from_user.username if update.message.from_user else None,
        action=ModerationAction.AUTO_SPAM,
        reason=reason,
        group_chat_id=chat.id,
        is_automatic=True
    ).insert()

    # Supprimer le message
    try:
        await update.message.delete()
    except Exception:
        pass

    # Appliquer un mute de 5 minutes pour la première infraction
    try:
        mute_duration = 300  # 5 minutes
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            ),
            until_date=datetime.now(UTC) + timedelta(seconds=mute_duration)
        )

        await context.bot.send_message(
            chat_id=chat.id,
            text=f"🔇 *Spam détecté*\n\nUtilisateur muet pour 5 minutes\nRaison : {reason}"
        )
    except Exception:
        pass


def register_group_handlers(application) -> None:
    """Enregistre les handlers de groupe."""

    # Gestion des membres du groupe
    application.add_handler(ChatMemberHandler(handle_new_chat_member, ChatMemberHandler.CHAT_MEMBER))

    # Modération des messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_moderation))

    # Callbacks de configuration groupe
    application.add_handler(CallbackQueryHandler(show_group_config, pattern=r"^group:config:\d+$"))
    application.add_handler(CallbackQueryHandler(toggle_auto_moderation, pattern=r"^group:auto_mod:\d+$"))
    application.add_handler(CallbackQueryHandler(show_group_rules, pattern=r"^group:rules:\d+$"))

    logger.info("Handlers groupe/canal enregistrés")
