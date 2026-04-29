"""
Orbi — Handlers Module Productivité (Phase 7).
Tâches, Notes, et Mode Focus (Pomodoro).
Conforme au CdC §6 : Module Productivité.
"""

import logging
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.bot.keyboards import CB_HOME, CB_MODULE_PRODUCTIVITY
from src.core.i18n import t
from src.models.productivity import TaskPriority
from src.models.user import User
from src.services.productivity_service import (
    create_note,
    create_task,
    delete_note,
    delete_task,
    get_active_focus_session,
    get_task,
    get_user_notes,
    get_user_tasks,
    start_focus_session,
    stop_focus_session,
    toggle_task_completion,
)

logger = logging.getLogger("orbi.handlers.productivity")

# ── États Tâches & Notes ──
STATE_TASK_TITLE = 1
STATE_NOTE_CONTENT = 2

# ─────────────────────────────────────
# Mode Focus (Pomodoro)
# ─────────────────────────────────────

async def show_focus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu du Mode Focus."""
    query = update.callback_query
    await query.answer()

    if context.user_data is None: return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    session = await get_active_focus_session(db_user.telegram_id)

    if session and session["status"] == "running":
        start_time = datetime.fromisoformat(session["start_time"])
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() / 60
        remaining = max(0, session["duration_minutes"] - elapsed)

        text = (
            f"⏳ <b>{t('productivity.focus_active', lang)}</b>\n\n"
            f"Type: {session['type'].title()}\n"
            f"Temps restant: {int(remaining)} min\n"
        )
        buttons = [
            [InlineKeyboardButton("🛑 Arrêter le focus", callback_data="focus:stop")],
            [InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_PRODUCTIVITY)],
        ]
    else:
        text = (
            f"🍅 <b>{t('productivity.focus', lang)}</b>\n\n"
            "Bloquez les notifications et restez concentré.\nChoisissez une durée :"
        )
        buttons = [
            [
                InlineKeyboardButton("🍅 Pomodoro (25m)", callback_data="focus:start:25"),
                InlineKeyboardButton("⏱️ Rapide (15m)", callback_data="focus:start:15"),
            ],
            [
                InlineKeyboardButton("🧠 Profond (50m)", callback_data="focus:start:50"),
                InlineKeyboardButton("🎓 Étude (90m)", callback_data="focus:start:90"),
            ],
            [InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_PRODUCTIVITY)],
        ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def start_focus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Démarre une session Focus."""
    query = update.callback_query
    db_user: User = context.user_data.get("db_user")

    duration = int(query.data.split(":")[2])
    await start_focus_session(db_user.telegram_id, duration)

    await query.answer(f"✅ Session de {duration} min démarrée !")
    await show_focus(update, context)


async def stop_focus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Arrête la session Focus."""
    query = update.callback_query
    db_user: User = context.user_data.get("db_user")

    await stop_focus_session(db_user.telegram_id)
    await query.answer("🛑 Session arrêtée.")
    await show_focus(update, context)


# ─────────────────────────────────────
# Gestion des Tâches
# ─────────────────────────────────────

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la liste des tâches non terminées."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    tasks = await get_user_tasks(db_user.telegram_id, limit=10, include_completed=False)

    text = f"✅ <b>{t('productivity.tasks', lang)}</b>\n\n"
    buttons = []

    if tasks:
        prio_icons = {TaskPriority.LOW: "🟢", TaskPriority.MEDIUM: "🟡", TaskPriority.HIGH: "🔴"}
        for tsk in tasks:
            icon = prio_icons.get(tsk.priority, "🟡")
            text += f"{icon} {tsk.title[:30]}\n"
            buttons.append([
                InlineKeyboardButton(f"✅ Terminer: {tsk.title[:20]}", callback_data=f"task_toggle:{tsk.id}"),
                InlineKeyboardButton("🗑️", callback_data=f"task_del:{tsk.id}"),
            ])
    else:
        text += "<i>Aucune tâche en cours. 🎉</i>\n"

    buttons.append([InlineKeyboardButton(t("productivity.add_task", lang), callback_data="prod:task_new")])
    buttons.append([InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_PRODUCTIVITY)])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_task_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marque une tâche comme terminée/en cours."""
    query = update.callback_query
    task_id = query.data.split(":")[1]

    tsk = await get_task(task_id)
    if tsk:
        await toggle_task_completion(tsk)
        await query.answer("✅ Tâche mise à jour.")
    
    await show_tasks(update, context)


async def handle_task_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Supprime une tâche."""
    query = update.callback_query
    task_id = query.data.split(":")[1]

    tsk = await get_task(task_id)
    if tsk:
        await delete_task(tsk)
        await query.answer("🗑️ Tâche supprimée.")
    
    await show_tasks(update, context)


# Création de tâche (Conversation)

async def start_task_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Demande le titre de la nouvelle tâche."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "fr")
    msg = {"fr": "✏️ Entrez la description de la tâche :", "en": "✏️ Enter task description:", "ar": "✏️ أدخل وصف المهمة:"}

    await query.edit_message_text(
        msg.get(lang, msg["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.cancel", lang), callback_data="prod_cancel")]
        ]),
    )
    return STATE_TASK_TITLE


async def handle_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Crée la tâche avec une échéance par défaut de +24h."""
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")
    title = update.message.text.strip()

    # Par défaut, échéance à demain, priorité moyenne
    due = datetime.now(timezone.utc) + timedelta(days=1)
    await create_task(db_user.telegram_id, title, due_date=due)

    confirm = {"fr": "✅ Tâche ajoutée (échéance demain).", "en": "✅ Task added.", "ar": "✅ تم إضافة المهمة."}
    
    await update.message.reply_text(
        confirm.get(lang, confirm["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("productivity.tasks", lang), callback_data="prod:tasks")],
            [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
        ]),
    )
    return ConversationHandler.END


# ─────────────────────────────────────
# Notes Personnelles
# ─────────────────────────────────────

async def show_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les dernières notes."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    notes = await get_user_notes(db_user.telegram_id, limit=5)

    text = f"📝 <b>{t('productivity.notes', lang)}</b>\n\n"
    buttons = []

    if notes:
        for n in notes:
            date_str = n.created_at.strftime("%d/%m")
            tags = " ".join([f"#{t}" for t in n.hashtags])
            text += f"▪️ [{date_str}] {n.content[:50]}... {tags}\n"
    else:
        text += "<i>Aucune note enregistrée.</i>\n"

    buttons.append([InlineKeyboardButton(t("productivity.add_note", lang), callback_data="prod:note_new")])
    buttons.append([InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_PRODUCTIVITY)])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def start_note_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Demande le contenu de la note."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "fr")
    msg = {"fr": "✏️ Écrivez votre note (ajoutez des #hashtags pour classer) :", 
           "en": "✏️ Write your note (add #hashtags to categorize):", 
           "ar": "✏️ اكتب ملاحظتك (أضف # للوسوم):"}

    await query.edit_message_text(
        msg.get(lang, msg["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.cancel", lang), callback_data="prod_cancel")]
        ]),
    )
    return STATE_NOTE_CONTENT


async def handle_note_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Crée la note à partir du texte envoyé."""
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")
    content = update.message.text.strip()

    note = await create_note(db_user.telegram_id, content)

    confirm = {"fr": f"✅ Note sauvegardée avec {len(note.hashtags)} hashtag(s).",
               "en": f"✅ Note saved with {len(note.hashtags)} hashtag(s).",
               "ar": f"✅ تم حفظ الملاحظة مع {len(note.hashtags)} وسم."}
    
    await update.message.reply_text(
        confirm.get(lang, confirm["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("productivity.notes", lang), callback_data="prod:notes")],
            [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
        ]),
    )
    return ConversationHandler.END


async def cancel_productivity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Annule toute action de création (Tâche ou Note)."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "fr")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("productivity.tasks", lang), callback_data="prod:tasks")],
        [InlineKeyboardButton(t("productivity.notes", lang), callback_data="prod:notes")],
        [InlineKeyboardButton(t("productivity.focus", lang), callback_data="prod:focus")],
        [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
    ])

    await query.edit_message_text(t("productivity.menu_title", lang), reply_markup=keyboard)
    return ConversationHandler.END


# ─────────────────────────────────────
# Registration
# ─────────────────────────────────────

def register_productivity_handlers(application) -> None:
    """Enregistre tous les handlers du module Productivité."""

    # Mode Focus
    application.add_handler(CallbackQueryHandler(show_focus, pattern=r"^prod:focus$"))
    application.add_handler(CallbackQueryHandler(start_focus, pattern=r"^focus:start:"))
    application.add_handler(CallbackQueryHandler(stop_focus, pattern=r"^focus:stop$"))

    # Tâches List/Toggle/Delete
    application.add_handler(CallbackQueryHandler(show_tasks, pattern=r"^prod:tasks$"))
    application.add_handler(CallbackQueryHandler(handle_task_toggle, pattern=r"^task_toggle:"))
    application.add_handler(CallbackQueryHandler(handle_task_delete, pattern=r"^task_del:"))

    # Notes List
    application.add_handler(CallbackQueryHandler(show_notes, pattern=r"^prod:notes$"))

    # Création Tâche (Conv)
    task_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_task_creation, pattern=r"^prod:task_new$")],
        states={
            STATE_TASK_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_task_title),
                CallbackQueryHandler(cancel_productivity, pattern=r"^prod_cancel$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_productivity, pattern=r"^prod_cancel$")],
        per_message=False,
    )
    application.add_handler(task_conv)

    # Création Note (Conv)
    note_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_note_creation, pattern=r"^prod:note_new$")],
        states={
            STATE_NOTE_CONTENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_note_content),
                CallbackQueryHandler(cancel_productivity, pattern=r"^prod_cancel$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_productivity, pattern=r"^prod_cancel$")],
        per_message=False,
    )
    application.add_handler(note_conv)

    logger.info("Handlers productivité enregistrés")
