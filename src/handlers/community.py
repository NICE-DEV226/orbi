"""
Orbi — Handlers Module Communauté (Phase 6).
Sondages et Leaderboard Karma.
Conforme au CdC §5 : Module Communauté / Enquêtes.
"""

import logging
from datetime import UTC, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.bot.keyboards import CB_HOME, CB_MODULE_COMMUNITY
from src.core.i18n import t
from src.models.user import User
from src.services.community_service import (
    close_poll,
    create_poll,
    get_active_polls,
    get_poll,
    get_top_karma_users,
    vote_poll,
)

logger = logging.getLogger("orbi.handlers.community")

# ── États Création Sondage ──
STATE_POLL_QUESTION = 1
STATE_POLL_OPTIONS = 2


# ─────────────────────────────────────
# Sondages Actifs
# ─────────────────────────────────────

async def show_polls(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la liste des sondages actifs."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    polls = await get_active_polls(limit=5)

    if not polls:
        text = {"fr": "📊 Aucun sondage en cours.", "en": "📊 No active polls.", "ar": "📊 لا توجد استطلاعات نشطة."}
        await query.edit_message_text(
            text.get(lang, text["fr"]),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("community.create_poll", lang), callback_data="community:poll_new")],
                [InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_COMMUNITY)],
            ]),
        )
        return

    text = f"📊 <b>{t('community.polls', lang)}</b>\n\n"
    buttons = []

    for p in polls:
        text += f"🔹 {p.question} ({p.total_votes} votes)\n"
        buttons.append([InlineKeyboardButton(f"🗳️ {p.question[:20]}...", callback_data=f"poll_view:{p.id}")])

    buttons.append([InlineKeyboardButton(t("community.create_poll", lang), callback_data="community:poll_new")])
    buttons.append([InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_COMMUNITY)])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def view_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche un sondage en détail pour voter."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    poll_id = query.data.split(":")[1]
    poll = await get_poll(poll_id)

    if not poll:
        await query.edit_message_text(t("errors.not_found", lang))
        return

    db_user: User = context.user_data.get("db_user")
    has_voted = db_user.telegram_id in poll.voters

    text = f"📊 <b>{poll.question}</b>\n\n"
    buttons = []

    for i, opt in enumerate(poll.options):
        qty = opt["votes"]
        pct = (qty / poll.total_votes * 100) if poll.total_votes > 0 else 0
        text += f"▪️ {opt['text']} — {qty} votes ({pct:.1f}%)\n"

        if not has_voted and poll.is_active:
            buttons.append([InlineKeyboardButton(f"Voter : {opt['text']}", callback_data=f"poll_vote:{poll.id}:{i}")])

    text += f"\nTotal des votes : {poll.total_votes}\n"
    if has_voted:
        text += "\n✅ Vous avez déjà voté."
    elif not poll.is_active:
        text += "\n❌ Sondage terminé."

    if poll.creator_telegram_id == db_user.telegram_id and poll.is_active:
        buttons.append([InlineKeyboardButton("🛑 Clôturer le sondage", callback_data=f"poll_close:{poll.id}")])

    buttons.append([InlineKeyboardButton(t("common.back", lang), callback_data="community:polls")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Traite un vote."""
    query = update.callback_query
    parts = query.data.split(":")
    poll_id = parts[1]
    if not context.user_data:
        return
    option_idx = int(parts[2])

    poll = await get_poll(poll_id)
    if not poll:
        await query.answer("Sondage introuvable.", show_alert=True)
        return

    db_user: User = context.user_data.get("db_user")
    success, error = await vote_poll(poll, db_user.telegram_id, [option_idx])

    if success:
        await query.answer("✅ Vote enregistré !")
        await view_poll(update, context)
    else:
        await query.answer(f"❌ {error}", show_alert=True)


async def handle_close_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clôture un sondage."""
    query = update.callback_query
    if not context.user_data:
        return
    poll_id = query.data.split(":")[1]
    poll = await get_poll(poll_id)
    db_user: User = context.user_data.get("db_user")

    if poll and poll.creator_telegram_id == db_user.telegram_id:
        await close_poll(poll)
        await query.answer("✅ Sondage clôturé.")
        await view_poll(update, context)
    else:
        await query.answer("❌ Non autorisé.", show_alert=True)


# ─────────────────────────────────────
# Création de Sondage (ConversationHandler)
# ─────────────────────────────────────

async def start_poll_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Démarre la création d'un sondage."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    msg = {
        "fr": "📝 <b>Nouveau sondage</b>\n\nQuelle est votre question ?",
        "en": "📝 <b>New poll</b>\n\nWhat is your question?",
        "ar": "📝 <b>استطلاع جديد</b>\n\nما هو سؤالك؟",
    }

    await query.edit_message_text(
        msg.get(lang, msg["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.cancel", lang), callback_data="poll_create_cancel")]
        ]),
        parse_mode="HTML"
    )
    return STATE_POLL_QUESTION


async def poll_question_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Question reçue → demander les options."""
    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")
    context.user_data["_poll_question"] = update.message.text.strip()

    msg = {
        "fr": "Parfait. Maintenant, envoyez les options de réponse, séparées par une virgule (ex: Oui, Non, Peut-être).",
        "en": "Perfect. Now send the answer options, separated by a comma (e.g., Yes, No, Maybe).",
        "ar": "ممتاز. الآن أرسل خيارات الإجابة مفصولة بفاصلة (مثال: نعم، لا، ربما).",
    }

    await update.message.reply_text(
        msg.get(lang, msg["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.cancel", lang), callback_data="poll_create_cancel")]
        ]),
    )
    return STATE_POLL_OPTIONS


async def poll_options_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Options reçues → créer le sondage."""
    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    question = context.user_data.pop("_poll_question")
    raw_options = update.message.text.split(",")
    options = [opt.strip() for opt in raw_options if opt.strip()]

    if len(options) < 2:
        await update.message.reply_text("❌ Il faut au moins 2 options.")
        return STATE_POLL_OPTIONS

    # Création du sondage (valide pendant 24h par défaut)
    end_date = datetime.now(UTC) + timedelta(days=1)
    poll = await create_poll(question, options, db_user.telegram_id, end_date=end_date)

    msg = {
        "fr": f"✅ Sondage créé !\n\n<b>{poll.question}</b>",
        "en": f"✅ Poll created!\n\n<b>{poll.question}</b>",
        "ar": f"✅ تم إنشاء الاستطلاع!\n\n<b>{poll.question}</b>",
    }

    await update.message.reply_text(
        msg.get(lang, msg["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Voir les sondages", callback_data="community:polls")],
            [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
        ]),
        parse_mode="HTML"
    )
    return ConversationHandler.END


async def cancel_poll_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Annule la création du sondage."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    context.user_data.pop("_poll_question", None)
    await show_polls(update, context)
    return ConversationHandler.END


# ─────────────────────────────────────
# Leaderboard Karma
# ─────────────────────────────────────

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le top 10 des utilisateurs avec le plus de Karma."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    top_users = await get_top_karma_users(limit=10)

    text = f"🏆 <b>{t('community.leaderboard', lang)}</b>\n\n"
    text += f"Votre Karma : <b>{db_user.karma_points}</b>\n\n"

    for i, u in enumerate(top_users):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
        text += f"{medal} <b>{u.display_name}</b> — {u.karma_points} pts\n"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_COMMUNITY)],
        ]),
    )


# ─────────────────────────────────────
# Registration
# ─────────────────────────────────────

def register_community_handlers(application) -> None:
    """Enregistre tous les handlers du module Communauté."""

    # Leaderboard
    application.add_handler(CallbackQueryHandler(show_leaderboard, pattern=r"^community:leaderboard$"))

    # Sondages (Lecture, Vote, Clôture)
    application.add_handler(CallbackQueryHandler(show_polls, pattern=r"^community:polls$"))
    application.add_handler(CallbackQueryHandler(view_poll, pattern=r"^poll_view:"))
    application.add_handler(CallbackQueryHandler(handle_vote, pattern=r"^poll_vote:"))
    application.add_handler(CallbackQueryHandler(handle_close_poll, pattern=r"^poll_close:"))

    # Création Sondage (Conversation)
    poll_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_poll_creation, pattern=r"^community:poll_new$")],
        states={
            STATE_POLL_QUESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, poll_question_received),
                CallbackQueryHandler(cancel_poll_creation, pattern=r"^poll_create_cancel$"),
            ],
            STATE_POLL_OPTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, poll_options_received),
                CallbackQueryHandler(cancel_poll_creation, pattern=r"^poll_create_cancel$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_poll_creation, pattern=r"^poll_create_cancel$")],
        per_message=False,
    )
    application.add_handler(poll_conv)

    logger.info("Handlers communauté enregistrés")
