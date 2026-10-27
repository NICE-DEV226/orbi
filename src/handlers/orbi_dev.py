"""
Orbi — Boutons des notifications Orbi Dev (réessayer, vérifier maintenant).

Le propriétaire est toujours celui qui appuie (`query.from_user`) : un message transféré à quelqu'un d'autre ne
donne accès à rien, le service ne retrouve que les données de l'appuyeur.
"""

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ContextTypes

from src.models.user import User
from src.orbi_dev import runner, service
from src.orbi_dev.access import can_use_orbi_dev
from src.orbi_dev.notifier import CB_CHECK, CB_RETRY, build_keyboard

logger = logging.getLogger("orbi.handlers.orbi_dev")


async def _launch_safely(owner_id: int, execution_id: str) -> None:
    try:
        await runner.launch_execution(owner_id, execution_id)
    except Exception:
        logger.exception("Lancement %s en échec", execution_id)


async def _authorize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    query = update.callback_query
    db_user: User | None = (context.user_data or {}).get("db_user")
    if not can_use_orbi_dev(db_user):
        await query.answer("Accès refusé.", show_alert=True)
        return None
    return query.from_user.id


async def retry_execution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Nouvelle tentative de la tâche d'une exécution échouée."""
    query = update.callback_query
    owner_id = await _authorize(update, context)
    if owner_id is None:
        return
    try:
        previous = await service.get_execution(owner_id, query.data.removeprefix(CB_RETRY))
        execution = await service.create_execution(owner_id, previous.task_id)
    except service.NotFoundError:
        await query.answer("Exécution introuvable.", show_alert=True)
        return
    except service.ConflictError:
        await query.answer("Une tentative est déjà en cours pour cette tâche.", show_alert=True)
        return
    context.application.create_task(_launch_safely(owner_id, str(execution.id)))
    await query.answer("Nouvelle tentative lancée.")
    await _drop_action(query, previous)


async def check_execution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Interroge le fournisseur tout de suite pour une exécution « à vérifier »."""
    query = update.callback_query
    owner_id = await _authorize(update, context)
    if owner_id is None:
        return
    try:
        execution = await runner.refresh_execution(owner_id, query.data.removeprefix(CB_CHECK))
    except service.NotFoundError:
        await query.answer("Exécution introuvable.", show_alert=True)
        return
    await query.answer("Vérification faite. Vous serez prévenu si l'état change.")
    await _drop_action(query, execution)


async def _drop_action(query, execution) -> None:
    """Retire le bouton d'action (évite un double clic) en gardant « Ouvrir » et « Voir la PR »."""
    try:
        await query.edit_message_reply_markup(reply_markup=build_keyboard(execution, with_action=False))
    except BadRequest as e:
        logger.debug("Clavier de notification inchangé : %s", e)


def register_orbi_dev_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(retry_execution, pattern=rf"^{CB_RETRY}"))
    application.add_handler(CallbackQueryHandler(check_execution, pattern=rf"^{CB_CHECK}"))
