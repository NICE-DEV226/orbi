"""
Orbi — APScheduler : tâches planifiées (Phase 4).
SLA alerts, CSAT reminders, morning brief, task reminders.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger("orbi.services.scheduler")

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Retourne le scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={"coalesce": True, "max_instances": 1},
        )
    return _scheduler


async def start_scheduler(bot) -> None:
    """Démarre le scheduler et enregistre les jobs récurrents."""
    scheduler = get_scheduler()

    # Stocker la référence au bot pour les jobs
    scheduler.bot = bot

    # ── Job : Vérification SLA (toutes les 5 minutes) ──
    scheduler.add_job(
        _check_sla_job,
        "interval",
        minutes=5,
        id="check_sla",
        replace_existing=True,
    )

    # ── Job : Rappel CSAT (toutes les heures) ──
    scheduler.add_job(
        _csat_reminder_job,
        "interval",
        hours=1,
        id="csat_reminder",
        replace_existing=True,
    )

    # ── Job : Rappel Tâches (toutes les 15 minutes) ──
    scheduler.add_job(
        _task_reminders_job,
        "interval",
        minutes=15,
        id="task_reminders",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("APScheduler démarré (jobs: check_sla, csat_reminder, task_reminders)")

async def stop_scheduler() -> None:
    """Arrête le scheduler proprement."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler arrêté")
    _scheduler = None

async def _task_reminders_job() -> None:
    """Job : envoie les rappels pour les tâches dont l'échéance est passée ou imminente."""
    try:
        from src.services.productivity_service import get_pending_reminders
        from src.services.notification_service import send_notification
        
        pending_tasks = await get_pending_reminders()
        scheduler = get_scheduler()
        bot = getattr(scheduler, "bot", None)

        if not bot or not pending_tasks:
            return

        for task in pending_tasks:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            # On marque le rappel comme envoyé pour ne pas spammer
            task.has_reminder = False
            await task.save()

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Marquer comme terminée", callback_data=f"task_toggle:{task.id}")],
                [InlineKeyboardButton("📝 Voir mes tâches", callback_data="prod:tasks")]
            ])

            text = f"⏰ <b>Rappel de tâche</b>\n\nLa tâche <b>{task.title}</b> est arrivée à échéance."
            
            await send_notification(bot, task.user_telegram_id, text, reply_markup=keyboard)

        logger.info("Rappels de tâches envoyés: %d", len(pending_tasks))

    except Exception as e:
        logger.error("Erreur dans _task_reminders_job: %s", e, exc_info=True)


async def _check_sla_job() -> None:
    """Job : vérifie les tickets en breach SLA et alerte l'admin."""
    try:
        from src.core.config import get_settings
        from src.services.notification_service import send_admin_alert
        from src.services.ticket_service import check_sla_breaches

        breached = await check_sla_breaches()

        if breached:
            settings = get_settings()
            scheduler = get_scheduler()
            bot = getattr(scheduler, "bot", None)

            if bot and settings.ADMIN_CHAT_ID:
                for ticket in breached:
                    await send_admin_alert(
                        bot,
                        settings.ADMIN_CHAT_ID,
                        "SLA Dépassé",
                        (
                            f"🎫 Ticket: <b>{ticket.ticket_id}</b>\n"
                            f"📂 Catégorie: {ticket.category}\n"
                            f"📝 Sujet: {ticket.subject}\n"
                            f"⏰ Priorité: {ticket.priority}\n"
                            f"👤 Utilisateur: {ticket.user_name}\n"
                            f"⏱️ Deadline: {ticket.sla_deadline}"
                        ),
                    )

            logger.info("SLA check: %d tickets en breach", len(breached))

    except Exception as e:
        logger.error("Erreur dans _check_sla_job: %s", e, exc_info=True)


async def _csat_reminder_job() -> None:
    """Job : envoie un rappel CSAT pour les tickets résolus sans évaluation."""
    try:
        from src.core.i18n import t
        from src.services.notification_service import send_notification
        from src.services.ticket_service import get_pending_csat_tickets

        pending = await get_pending_csat_tickets()
        scheduler = get_scheduler()
        bot = getattr(scheduler, "bot", None)

        if not bot:
            return

        for ticket in pending:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            # Clavier CSAT 1-5
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"{'⭐' * i}", callback_data=f"csat:{ticket.ticket_id}:{i}")
                    for i in range(1, 6)
                ]
            ])

            lang = "fr"  # On prendra la langue du user en réalité
            text = t("notifications.csat_request", lang, ticket_id=ticket.ticket_id)

            success = await send_notification(
                bot, ticket.user_telegram_id, text, reply_markup=keyboard,
            )

            if success:
                ticket.csat_reminder_sent = True
                await ticket.save()

        if pending:
            logger.info("CSAT reminders envoyés: %d", len(pending))

    except Exception as e:
        logger.error("Erreur dans _csat_reminder_job: %s", e, exc_info=True)
