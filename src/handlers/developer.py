"""
Orbi — Handlers Module Développeur (Phase 8).
Logs d'erreurs, Statistiques d'infrastructure, Événements GitHub.
Réservé aux admins (géré par middleware ou vérification de `is_admin`).
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from src.bot.keyboards import CB_HOME, CB_MODULE_DEVELOPERS
from src.core.i18n import t
from src.models.user import User
from src.services.developer_service import (
    get_api_logs_stats,
    get_recent_github_events,
    get_redis_stats,
    get_unresolved_errors,
    resolve_error,
)

logger = logging.getLogger("orbi.handlers.developer")

# ─────────────────────────────────────
# Sécurité locale
# ─────────────────────────────────────
def is_admin(user: User) -> bool:
    """Vérifie si l'utilisateur est admin."""
    return user.role in ["admin", "superadmin"]

# ─────────────────────────────────────
# Événements GitHub
# ─────────────────────────────────────

async def show_github_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les 5 derniers webhooks reçus de GitHub."""
    query = update.callback_query
    await query.answer()

    if context.user_data is None: return
    db_user: User = context.user_data.get("db_user")
    if not db_user or not is_admin(db_user):
        await query.answer("Accès refusé !", show_alert=True)
        return

    events = await get_recent_github_events(limit=5)
    
    text = f"🐙 <b>Derniers événements GitHub</b>\n\n"
    
    if not events:
        text += "Aucun événement récent enregistré.\n"
    else:
        for ev in events:
            date_str = ev.received_at.strftime("%d/%m %H:%M")
            repo = ev.repository.split("/")[-1]
            text += f"▪️ <b>[{date_str}] {ev.event_type}</b> sur {repo} by {ev.sender}\n"
            
            # Détails extraits
            if ev.payload_details:
                if "message" in ev.payload_details:
                    text += f"   💬 <i>{ev.payload_details['message'][:50]}...</i>\n"
                elif "title" in ev.payload_details:
                    text += f"   📌 <i>{ev.payload_details['title']} ({ev.payload_details.get('state', '')})</i>\n"

    buttons = [[InlineKeyboardButton(t("common.back", context.user_data.get("lang", "fr")), callback_data=CB_MODULE_DEVELOPERS)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────
# Statistiques Infrastructure (API & Redis)
# ─────────────────────────────────────

async def show_infra_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les stats de l'API (MongoDB) et de Redis."""
    query = update.callback_query
    await query.answer()

    if context.user_data is None: return
    db_user: User = context.user_data.get("db_user")
    if not db_user or not is_admin(db_user):
        await query.answer("Accès refusé !", show_alert=True)
        return

    # On récupère les deux de façon asynchrone pour ne pas bloquer
    import asyncio
    api_stats, redis_stats = await asyncio.gather(
        get_api_logs_stats(),
        get_redis_stats()
    )

    text = f"⚙️ <b>Statistiques Infrastructures</b>\n\n"
    text += f"🌐 <b>API & Backend :</b>\n"
    text += f"├ Appels totaux : {api_stats.get('total_calls', 0)}\n"
    text += f"├ Succès (Ratio) : {api_stats.get('success_rate', 100)}%\n"
    text += f"├ Erreurs client (4xx) : {api_stats.get('client_errors', 0)}\n"
    text += f"└ Erreurs serveur (5xx) : {api_stats.get('server_errors', 0)}\n\n"
    
    text += f"🧠 <b>Cache Redis :</b>\n"
    if "error" in redis_stats:
        text += f"└ ⚠️ Erreur: {redis_stats['error']}\n"
    else:
        text += f"├ Version : {redis_stats.get('version')}\n"
        text += f"├ Uptime : {redis_stats.get('uptime_days')} jours\n"
        text += f"├ Clients co : {redis_stats.get('connected_clients')}\n"
        text += f"└ Mémoire utilisée : {redis_stats.get('used_memory_human')}\n"

    buttons = [[InlineKeyboardButton(t("common.back", context.user_data.get("lang", "fr")), callback_data=CB_MODULE_DEVELOPERS)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────
# Centre des Erreurs (Logs)
# ─────────────────────────────────────

async def show_error_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la liste des erreurs non résolues."""
    query = update.callback_query
    await query.answer()

    if context.user_data is None: return
    db_user: User = context.user_data.get("db_user")
    if not db_user or not is_admin(db_user):
        await query.answer("Accès refusé !", show_alert=True)
        return

    errors = await get_unresolved_errors(limit=5)
    
    text = f"⚠️ <b>Centre des erreurs</b>\n\n"
    buttons = []

    if not errors:
        text += "✅ Aucun problème signalé. Le système est stable."
    else:
        for err in errors:
            date_str = err.occurred_at.strftime("%d/%m %H:%M")
            text += f"▪️ [{date_str}] <b>{err.service}</b>\n"
            text += f"   ❌ {err.error_message[:40]}...\n"
            
            buttons.append([InlineKeyboardButton(f"✅ Marquer résolu ({err.service})", callback_data=f"dev_err_resolve:{err.id}")])

    buttons.append([InlineKeyboardButton(t("common.back", context.user_data.get("lang", "fr")), callback_data=CB_MODULE_DEVELOPERS)])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_error_resolve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marque une erreur comme résolue."""
    query = update.callback_query
    
    db_user: User = context.user_data.get("db_user")
    if not is_admin(db_user):
        await query.answer("Accès refusé !", show_alert=True)
        return
        
    err_id = query.data.split(":")[1]
    res = await resolve_error(err_id, db_user.telegram_id)
    
    if res:
        await query.answer(f"✅ Erreur de '{res.service}' résolue.")
    else:
        await query.answer("❌ Erreur introuvable.", show_alert=True)
        
    await show_error_logs(update, context)


# ─────────────────────────────────────
# Registration
# ─────────────────────────────────────

def register_developer_handlers(application) -> None:
    """Enregistre tous les handlers du module Développeur."""

    application.add_handler(CallbackQueryHandler(show_github_events, pattern=r"^dev:github$"))
    application.add_handler(CallbackQueryHandler(show_infra_stats, pattern=r"^dev:stats$"))
    application.add_handler(CallbackQueryHandler(show_error_logs, pattern=r"^dev:logs$"))
    application.add_handler(CallbackQueryHandler(handle_error_resolve, pattern=r"^dev_err_resolve:"))

    logger.info("Handlers dev enregistrés (protégés admin)")
