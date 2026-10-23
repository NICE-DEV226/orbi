"""
Orbi — Handlers Module Support (Phase 4).
ConversationHandler guidé pour la création de ticket.
Affichage lista des tickets, réponse, résolution, CSAT.
Conforme au CdC §3 : Module Support complet.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.bot.keyboards import CB_HOME, CB_MODULE_SUPPORT
from src.core.i18n import t
from src.models.ticket import SLA_SECONDS, TicketCategory
from src.services.ticket_service import (
    MAX_OPEN_TICKETS,
    TicketLimitExceededError,
    add_message,
    count_open_tickets,
    create_ticket,
    get_ticket,
    get_user_tickets,
    resolve_ticket,
    save_csat_rating,
)

logger = logging.getLogger("orbi.handlers.support")

# ── États du ConversationHandler ──
STATE_CATEGORY = 0
STATE_SUBJECT = 1
STATE_DESCRIPTION = 2
STATE_CONFIRM = 3
STATE_REPLY = 4


# ─────────────────────────────────────
# Création de ticket (ConversationHandler)
# ─────────────────────────────────────

async def start_new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Étape 1 : Vérifier la limite puis afficher le sélecteur de catégorie."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    db_user = context.user_data.get("db_user")

    # Vérifier la limite de tickets ouverts
    open_count = await count_open_tickets(db_user.telegram_id)
    if open_count >= MAX_OPEN_TICKETS:
        if query:
            await query.edit_message_text(
                t("support.ticket_limit", lang, count=str(open_count)),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_SUPPORT)]
                ]),
            )
        return ConversationHandler.END

    # Afficher le sélecteur de catégorie
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("support.category_billing", lang), callback_data="ticket_cat:billing"),
            InlineKeyboardButton(t("support.category_technical", lang), callback_data="ticket_cat:technical"),
        ],
        [
            InlineKeyboardButton(t("support.category_general", lang), callback_data="ticket_cat:general"),
            InlineKeyboardButton(t("support.category_complaint", lang), callback_data="ticket_cat:complaint"),
        ],
        [
            InlineKeyboardButton(t("support.category_other", lang), callback_data="ticket_cat:other"),
        ],
        [InlineKeyboardButton(t("common.cancel", lang), callback_data="ticket_cancel")],
    ])

    await query.edit_message_text(
        t("support.category_select", lang),
        reply_markup=keyboard,
    )
    return STATE_CATEGORY


async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Étape 2 : Catégorie choisie → demander le sujet."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    category = query.data.split(":")[1]  # ticket_cat:billing → billing
    context.user_data["_ticket_category"] = category

    await query.edit_message_text(
        t("support.subject_prompt", lang),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.cancel", lang), callback_data="ticket_cancel")]
        ]),
    )
    return STATE_SUBJECT


async def subject_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Étape 3 : Sujet reçu → valider puis demander la description."""
    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")
    subject = update.message.text.strip()

    # Validation : 5-100 caractères
    if len(subject) < 5 or len(subject) > 100:
        await update.message.reply_text(
            t("support.subject_too_short", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("common.cancel", lang), callback_data="ticket_cancel")]
            ]),
        )
        return STATE_SUBJECT

    context.user_data["_ticket_subject"] = subject

    await update.message.reply_text(
        t("support.description_prompt", lang),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.cancel", lang), callback_data="ticket_cancel")]
        ]),
    )
    return STATE_DESCRIPTION


async def description_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Étape 4 : Description reçue → afficher le récapitulatif pour confirmation."""
    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")
    description = update.message.text.strip()

    # Validation : minimum 20 caractères
    if len(description) < 20:
        await update.message.reply_text(
            t("support.description_too_short", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("common.cancel", lang), callback_data="ticket_cancel")]
            ]),
        )
        return STATE_DESCRIPTION

    context.user_data["_ticket_description"] = description

    category = context.user_data["_ticket_category"]
    subject = context.user_data["_ticket_subject"]

    # Labels de catégorie localisés
    cat_labels = {
        "billing": t("support.category_billing", lang),
        "technical": t("support.category_technical", lang),
        "general": t("support.category_general", lang),
        "complaint": t("support.category_complaint", lang),
        "other": t("support.category_other", lang),
    }

    await update.message.reply_text(
        t("support.review_ticket", lang,
            category=cat_labels.get(category, category),
            subject=subject,
            description=description[:200] + ("..." if len(description) > 200 else ""),
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(t("common.confirm", lang), callback_data="ticket_confirm"),
                InlineKeyboardButton(t("common.cancel", lang), callback_data="ticket_cancel"),
            ]
        ]),
    )
    return STATE_CONFIRM


async def ticket_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Étape finale : Confirmer et créer le ticket."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    db_user = context.user_data.get("db_user")

    category = TicketCategory(context.user_data.pop("_ticket_category"))
    subject = context.user_data.pop("_ticket_subject")
    description = context.user_data.pop("_ticket_description")

    try:
        ticket = await create_ticket(db_user, category, subject, description, lang)

        # Formater le SLA pour l'affichage
        sla_seconds = SLA_SECONDS[ticket.priority]
        if sla_seconds >= 86400:
            sla_display = f"{sla_seconds // 86400}j"
        elif sla_seconds >= 3600:
            sla_display = f"{sla_seconds // 3600}h"
        else:
            sla_display = f"{sla_seconds // 60}min"

        prio_labels = {
            "fr": {"urgent": "🔴 Urgente", "high": "🟠 Haute", "medium": "🟡 Moyenne", "low": "🟢 Basse"},
            "en": {"urgent": "🔴 Urgent", "high": "🟠 High", "medium": "🟡 Medium", "low": "🟢 Low"},
            "ar": {"urgent": "🔴 عاجلة", "high": "🟠 عالية", "medium": "🟡 متوسطة", "low": "🟢 منخفضة"},
        }

        cat_labels = {
            "billing": t("support.category_billing", lang),
            "technical": t("support.category_technical", lang),
            "general": t("support.category_general", lang),
            "complaint": t("support.category_complaint", lang),
            "other": t("support.category_other", lang),
        }

        await query.edit_message_text(
            t("support.ticket_created", lang,
                ticket_id=ticket.ticket_id,
                category=cat_labels.get(category.value, category.value),
                subject=subject,
                priority=prio_labels.get(lang, prio_labels["fr"]).get(ticket.priority.value, ticket.priority.value),
                sla=sla_display,
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)]
            ]),
        )

    except TicketLimitExceededError as e:
        await query.edit_message_text(
            t("support.ticket_limit", lang, count=str(e.count)),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_SUPPORT)]
            ]),
        )

    except Exception as e:
        logger.error("Erreur création ticket: %s", e, exc_info=True)
        await query.edit_message_text(
            t("common.error", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)]
            ]),
        )

    return ConversationHandler.END


async def ticket_cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Annulation de la création de ticket."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")

    # Nettoyage du contexte
    if context.user_data is not None:
        context.user_data.pop("_ticket_category", None)
        context.user_data.pop("_ticket_subject", None)
        context.user_data.pop("_ticket_description", None)

    text = t("support.menu_title", lang)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("support.new_ticket", lang), callback_data="support:new_ticket"),
            InlineKeyboardButton(t("support.my_tickets", lang), callback_data="support:my_tickets"),
        ],
        [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
    ])

    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


# ─────────────────────────────────────
# Affichage des tickets
# ─────────────────────────────────────

async def show_my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la liste des tickets de l'utilisateur."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    db_user = context.user_data.get("db_user")

    tickets = await get_user_tickets(db_user.telegram_id, limit=10)

    if not tickets:
        no_tickets = {"fr": "📋 Vous n'avez aucun ticket.", "en": "📋 You have no tickets.", "ar": "📋 ليس لديك تذاكر."}
        await query.edit_message_text(
            no_tickets.get(lang, no_tickets["fr"]),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(t("support.new_ticket", lang), callback_data="support:new_ticket"),
                    InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME),
                ]
            ]),
        )
        return

    # Construire la liste des tickets
    status_emoji = {
        "open": "🟡", "in_progress": "🔵", "waiting_user": "🟠",
        "resolved": "🟢", "closed": "⚪",
    }

    lines = []
    buttons = []
    for tk in tickets:
        emoji = status_emoji.get(tk.status.value, "❓")
        lines.append(f"{emoji} <b>{tk.ticket_id}</b> — {tk.subject[:30]}")
        buttons.append([
            InlineKeyboardButton(
                f"{emoji} {tk.ticket_id}",
                callback_data=f"ticket_view:{tk.ticket_id}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(t("support.new_ticket", lang), callback_data="support:new_ticket"),
    ])
    buttons.append([InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)])

    header = {"fr": "📋 <b>Mes Tickets</b>\n\n", "en": "📋 <b>My Tickets</b>\n\n", "ar": "📋 <b>تذاكري</b>\n\n"}
    text = header.get(lang, header["fr"]) + "\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def view_ticket_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le détail d'un ticket avec actions disponibles."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    ticket_id = query.data.split(":")[1]  # ticket_view:TKT-2026-00001

    ticket = await get_ticket(ticket_id)
    if not ticket:
        await query.edit_message_text(
            t("errors.not_found", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("common.back", lang), callback_data="support:my_tickets")]
            ]),
        )
        return

    status_labels = {
        "fr": {"open": "Ouvert", "in_progress": "En cours", "waiting_user": "En attente de vous",
               "resolved": "Résolu", "closed": "Fermé"},
        "en": {"open": "Open", "in_progress": "In Progress", "waiting_user": "Waiting for you",
               "resolved": "Resolved", "closed": "Closed"},
        "ar": {"open": "مفتوح", "in_progress": "قيد المعالجة", "waiting_user": "في انتظارك",
               "resolved": "محلول", "closed": "مغلق"},
    }

    cat_labels = {
        "billing": t("support.category_billing", lang),
        "technical": t("support.category_technical", lang),
        "general": t("support.category_general", lang),
        "complaint": t("support.category_complaint", lang),
        "other": t("support.category_other", lang),
    }

    status = status_labels.get(lang, status_labels["fr"]).get(ticket.status.value, ticket.status.value)
    category = cat_labels.get(ticket.category.value, ticket.category.value)

    # Dernier message
    last_msg = ""
    if ticket.messages:
        last = ticket.messages[-1]
        role_label = {"user": "👤", "agent": "🎧"}.get(last.get("role", ""), "")
        last_msg = f"\n\n💬 Dernier message : {role_label} {last.get('text', '')[:100]}"

    text = (
        f"🎫 <b>Ticket {ticket.ticket_id}</b>\n\n"
        f"📂 Catégorie : {category}\n"
        f"📝 Sujet : {ticket.subject}\n"
        f"📊 Statut : {status}\n"
        f"⏰ Créé le : {ticket.created_at.strftime('%d/%m/%Y %H:%M')}"
        f"{'  ⚠️ SLA dépassé' if ticket.sla_breached else ''}"
        f"{last_msg}"
    )

    buttons = []
    if ticket.status not in ("resolved", "closed"):
        buttons.append([
            InlineKeyboardButton(t("support.reply", lang), callback_data=f"ticket_reply:{ticket.ticket_id}"),
            InlineKeyboardButton(t("support.mark_resolved", lang), callback_data=f"ticket_resolve:{ticket.ticket_id}"),
        ])

    buttons.append([InlineKeyboardButton(t("common.back", lang), callback_data="support:my_tickets")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────
# Réponse et résolution
# ─────────────────────────────────────

async def start_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Demande le message de réponse au ticket."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    ticket_id = query.data.split(":")[1]
    context.user_data["_replying_to_ticket"] = ticket_id

    prompt = {"fr": "✏️ Écrivez votre réponse :", "en": "✏️ Write your reply:", "ar": "✏️ اكتب ردك:"}

    await query.edit_message_text(
        prompt.get(lang, prompt["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.cancel", lang), callback_data=f"ticket_view:{ticket_id}")]
        ]),
    )


async def handle_ticket_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Traite le message de réponse au ticket."""
    ticket_id = context.user_data.get("_replying_to_ticket")
    if not ticket_id:
        return

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    text = update.message.text.strip()

    ticket = await get_ticket(ticket_id)
    if ticket:
        await add_message(ticket, "user", text)

    context.user_data.pop("_replying_to_ticket", None)

    confirm = {"fr": "✅ Réponse envoyée.", "en": "✅ Reply sent.", "ar": "✅ تم إرسال الرد."}

    await update.message.reply_text(
        confirm.get(lang, confirm["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("support.view_full", lang), callback_data=f"ticket_view:{ticket_id}")],
            [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
        ]),
    )


async def resolve_ticket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marque un ticket comme résolu puis propose le CSAT."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    ticket_id = query.data.split(":")[1]

    ticket = await get_ticket(ticket_id)
    if ticket:
        await resolve_ticket(ticket)

        # Proposer le CSAT immédiatement
        csat_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{'⭐' * i}", callback_data=f"csat:{ticket_id}:{i}") for i in range(1, 6)],
            [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
        ])

        await query.edit_message_text(
            t("support.ticket_closed", lang, ticket_id=ticket_id) + "\n\n" +
            t("notifications.csat_request", lang, ticket_id=ticket_id),
            reply_markup=csat_keyboard,
        )
    else:
        await query.edit_message_text(
            t("errors.not_found", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)]
            ]),
        )


# ─────────────────────────────────────
# CSAT
# ─────────────────────────────────────

async def handle_csat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enregistre la note CSAT."""
    query = update.callback_query
    await query.answer()

    if not context.user_data:

        return
    lang = context.user_data.get("lang", "fr")
    parts = query.data.split(":")  # csat:TKT-2026-00001:4
    ticket_id = parts[1]
    rating = int(parts[2])

    ticket = await get_ticket(ticket_id)
    if ticket:
        await save_csat_rating(ticket, rating)

    await query.edit_message_text(
        t("notifications.csat_thanks", lang),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)]
        ]),
    )


# ─────────────────────────────────────
# Escalade
# ─────────────────────────────────────

async def handle_escalation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Propose l'escalade quand le bot ne comprend pas."""
    if not context.user_data:
        return
    lang = context.user_data.get("lang", "fr")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("support.escalation_create", lang), callback_data="support:new_ticket"),
            InlineKeyboardButton(t("support.escalation_continue", lang), callback_data=CB_HOME),
        ]
    ])

    await update.message.reply_text(
        t("support.escalation", lang),
        reply_markup=keyboard,
    )


# ─────────────────────────────────────
# Registration
# ─────────────────────────────────────

def register_support_handlers(application) -> None:
    """Enregistre tous les handlers du module Support."""

    # ConversationHandler pour la création de ticket
    ticket_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_new_ticket, pattern=r"^support:new_ticket$"),
        ],
        states={
            STATE_CATEGORY: [
                CallbackQueryHandler(category_selected, pattern=r"^ticket_cat:"),
                CallbackQueryHandler(ticket_cancelled, pattern=r"^ticket_cancel$"),
            ],
            STATE_SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, subject_received),
                CallbackQueryHandler(ticket_cancelled, pattern=r"^ticket_cancel$"),
            ],
            STATE_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, description_received),
                CallbackQueryHandler(ticket_cancelled, pattern=r"^ticket_cancel$"),
            ],
            STATE_CONFIRM: [
                CallbackQueryHandler(ticket_confirmed, pattern=r"^ticket_confirm$"),
                CallbackQueryHandler(ticket_cancelled, pattern=r"^ticket_cancel$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(ticket_cancelled, pattern=r"^ticket_cancel$"),
        ],
        per_message=False,
    )

    application.add_handler(ticket_conv)

    # Affichage des tickets
    application.add_handler(CallbackQueryHandler(show_my_tickets, pattern=r"^support:my_tickets$"))
    application.add_handler(CallbackQueryHandler(view_ticket_detail, pattern=r"^ticket_view:"))
    application.add_handler(CallbackQueryHandler(start_reply, pattern=r"^ticket_reply:"))
    application.add_handler(CallbackQueryHandler(resolve_ticket_handler, pattern=r"^ticket_resolve:"))

    # Réponse textuelle aux tickets (group séparé pour ne pas interférer)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticket_reply),
        group=6,
    )

    # CSAT
    application.add_handler(CallbackQueryHandler(handle_csat, pattern=r"^csat:"))

    logger.info("Handlers support enregistrés")
