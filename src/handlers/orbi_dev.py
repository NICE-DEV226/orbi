"""
Orbi — Boutons des notifications Orbi Dev (réessayer, vérifier maintenant).

Le propriétaire est toujours celui qui appuie (`query.from_user`) : un message transféré à quelqu'un d'autre ne
donne accès à rien, le service ne retrouve que les données de l'appuyeur.
"""

import logging
import time

from telegram import ReplyParameters, Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ContextTypes

from src.core.text import esc
from src.models.user import User
from src.orbi_dev import cards, runner, service
from src.orbi_dev.access import can_use_orbi_dev
from src.orbi_dev.choices import (
    CB_GEN,
    CB_OPT,
    GENERIC_CHOICES,
    option_fingerprint,
    parsed_options,
)
from src.orbi_dev.connectors.base import ConnectorError, RemoteMessage
from src.orbi_dev.notifier import (
    CB_APPROVE,
    CB_CHECK,
    CB_IGNORE,
    CB_REPLY,
    CB_RETRY,
    CB_THREAD,
    build_keyboard,
)
from src.orbi_dev.present import ago
from src.orbi_dev.state import ExecutionStatus

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
    await cards.post_card(query.get_bot(), execution)  # la nouvelle tentative se suit sur sa propre carte


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
    if query.message.message_id == execution.card_message_id:
        await cards.update_cards(query.get_bot())  # la carte garde ses boutons et reflète l'état d'après
    else:
        await _drop_action(query, execution)


async def approve_execution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Validation humaine : l'exécution en attente passe en file et est lancée."""
    query = update.callback_query
    owner_id = await _authorize(update, context)
    if owner_id is None:
        return
    try:
        execution = await runner.approve_execution(owner_id, query.data.removeprefix(CB_APPROVE))
    except service.NotFoundError:
        await query.answer("Exécution introuvable.", show_alert=True)
        return
    except service.ConflictError:
        await query.answer("Cette exécution a déjà été traitée.", show_alert=True)
        return
    context.application.create_task(_launch_safely(owner_id, str(execution.id)))
    await query.answer("Exécution lancée.")
    await _drop_action(query, execution)
    if execution.card_message_id:
        await cards.update_cards(query.get_bot())
    else:
        await cards.post_card(query.get_bot(), execution)


async def ignore_execution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Refus humain : l'exécution en attente est annulée, rien n'est lancé."""
    query = update.callback_query
    owner_id = await _authorize(update, context)
    if owner_id is None:
        return
    try:
        execution = await runner.dismiss_execution(owner_id, query.data.removeprefix(CB_IGNORE))
    except service.NotFoundError:
        await query.answer("Exécution introuvable.", show_alert=True)
        return
    except service.ConflictError:
        await query.answer("Cette exécution a déjà été traitée.", show_alert=True)
        return
    await query.answer("Exécution ignorée.")
    await _drop_action(query, execution)
    if execution.card_message_id:
        await cards.update_cards(query.get_bot())


async def reply_to_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Remote control (ADR-0010) : « Répondre à l'agent » arme la saisie — le prochain message texte
    est transmis à l'exécution par `dev_hub.messages` → `runner.send_input_to_execution`.
    """
    query = update.callback_query
    owner_id = await _authorize(update, context)
    if owner_id is None:
        return
    execution_id = query.data.removeprefix(CB_REPLY)
    try:
        execution = await service.get_execution(owner_id, execution_id)
    except service.NotFoundError:
        await query.answer("Exécution introuvable.", show_alert=True)
        return
    if execution.status not in (ExecutionStatus.RUNNING, ExecutionStatus.NEEDS_ATTENTION) or not execution.external_id:
        await query.answer("L'agent n'accepte plus de message.", show_alert=True)
        return
    context.user_data["dev"] = {"step": "reply", "execution_id": execution_id, "at": time.monotonic()}
    await query.answer("Envoyez votre message : il sera transmis à l'agent.")


_ROLE_LABEL = {"user": "Vous", "agent": "Agent", "system": "Session"}
_THREAD_LIMIT = 4000
_THREAD_MAX_MESSAGES = 4


def _thread_text(messages: list[RemoteMessage]) -> list[str]:
    """Le fil en messages Telegram (HTML), découpé sur les frontières de message."""
    if not messages:
        return ["<i>Aucun message pour l'instant.</i>"]
    chunks: list[str] = []
    current = ""
    for m in messages:
        label = _ROLE_LABEL.get(m.role, m.role)
        when = f" · {ago(m.at)}" if m.at else ""
        block = f"<b>{label}</b><i>{when}</i>\n{esc(m.text)}\n\n"
        if len(current) + len(block) > _THREAD_LIMIT - 100 and current:
            chunks.append(current.rstrip())
            current = ""
        current += block
    if current:
        chunks.append(current.rstrip())
    if len(chunks) > _THREAD_MAX_MESSAGES:
        chunks = chunks[-_THREAD_MAX_MESSAGES:]
        chunks[0] = "<i>… messages plus anciens masqués …</i>\n\n" + chunks[0]
    return chunks


async def show_thread(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """« Fil de discussion » : lit les messages de la session chez le fournisseur (capacité HISTORY)."""
    query = update.callback_query
    owner_id = await _authorize(update, context)
    if owner_id is None:
        return
    execution_id = query.data.removeprefix(CB_THREAD)
    try:
        messages = await runner.get_execution_thread(owner_id, execution_id, limit=25)
    except service.NotFoundError:
        await query.answer("Exécution introuvable.", show_alert=True)
        return
    except service.ConflictError:
        await query.answer("Pas encore de session chez le fournisseur.", show_alert=True)
        return
    except ConnectorError as e:
        await query.answer(f"Fil indisponible ({e.category.value}).", show_alert=True)
        return
    await query.answer()
    for i, chunk in enumerate(_thread_text(messages)):
        kwargs = {"parse_mode": "HTML"}
        if i == 0:
            kwargs["reply_parameters"] = ReplyParameters(
                message_id=query.message.message_id, allow_sending_without_reply=True
            )
        await query.message.reply_text(chunk, **kwargs)


async def _drop_choices(query, execution) -> None:
    """Retire les boutons de choix (évite un double envoi) en gardant Répondre, Fil et liens."""
    try:
        can_interact = execution.status in (ExecutionStatus.RUNNING, ExecutionStatus.NEEDS_ATTENTION) and (
            await service.execution_interact_capable(execution.owner_id, execution)
        )
        can_history = bool(execution.external_id) and await service.execution_history_capable(
            execution.owner_id, execution
        )
        await query.edit_message_reply_markup(
            reply_markup=build_keyboard(execution, can_interact=can_interact, can_history=can_history)
        )
    except BadRequest as e:
        logger.debug("Clavier après choix inchangé : %s", e)


async def _send_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, owner_id: int,
                       execution_id: str, resolve) -> None:
    """Valide l'exécution puis transmet le choix résolu à l'agent (remote control, ADR-0010)."""
    query = update.callback_query
    try:
        execution = await service.get_execution(owner_id, execution_id)
    except service.NotFoundError:
        await query.answer("Exécution introuvable.", show_alert=True)
        return
    if execution.status not in (ExecutionStatus.RUNNING, ExecutionStatus.NEEDS_ATTENTION) or not execution.external_id:
        await query.answer("L'agent n'accepte plus de message.", show_alert=True)
        return
    text = await resolve(owner_id, execution)
    if text is None:
        await query.answer("Ce choix n'est plus d'actualité — ouvrez le fil de discussion.", show_alert=True)
        return
    try:
        await runner.send_input_to_execution(owner_id, execution_id, text)
    except service.NotFoundError:
        await query.answer("Exécution introuvable.", show_alert=True)
        return
    except (service.ConflictError, ValueError) as e:
        await query.answer(str(e), show_alert=True)
        return
    except ConnectorError as e:
        await query.answer(f"Message non transmis ({e.category.value}).", show_alert=True)
        return
    await query.answer("Choix transmis à l'agent.")
    try:
        fresh = await service.get_execution(owner_id, execution_id)
        await _drop_choices(query, fresh)
    except service.NotFoundError:
        pass
    try:
        context.application.create_task(cards.update_cards(context.bot))
    except Exception:
        logger.debug("Actualisation de carte après choix impossible", exc_info=True)


async def choose_parsed_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Option lue dans le message de l'agent : renvoyée telle quelle, après vérification d'empreinte."""
    query = update.callback_query
    owner_id = await _authorize(update, context)
    if owner_id is None:
        return
    parts = query.data.removeprefix(CB_OPT).split(":")
    if len(parts) != 3:
        await query.answer("Bouton invalide.", show_alert=True)
        return
    execution_id, index_s, fingerprint = parts

    async def resolve(owner, execution):
        try:
            index = int(index_s)
        except ValueError:
            return None
        options = await parsed_options(owner, execution)
        if not 0 <= index < len(options) or option_fingerprint(options[index]) != fingerprint:
            return None
        return options[index]

    await _send_choice(update, context, owner_id, execution_id, resolve)


async def choose_generic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Réponse générique suggérée quand le message de l'agent n'a pas de liste d'options lisible."""
    query = update.callback_query
    owner_id = await _authorize(update, context)
    if owner_id is None:
        return
    parts = query.data.removeprefix(CB_GEN).split(":")
    if len(parts) != 2:
        await query.answer("Bouton invalide.", show_alert=True)
        return
    execution_id, index_s = parts

    async def resolve(owner, execution):
        try:
            index = int(index_s)
        except ValueError:
            return None
        return GENERIC_CHOICES[index] if 0 <= index < len(GENERIC_CHOICES) else None

    await _send_choice(update, context, owner_id, execution_id, resolve)


async def _drop_action(query, execution) -> None:
    """Retire le bouton d'action (évite un double clic) en gardant « Ouvrir » et « Voir la PR »."""
    try:
        await query.edit_message_reply_markup(reply_markup=build_keyboard(execution, with_action=False))
    except BadRequest as e:
        logger.debug("Clavier de notification inchangé : %s", e)


def register_orbi_dev_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(retry_execution, pattern=rf"^{CB_RETRY}"))
    application.add_handler(CallbackQueryHandler(check_execution, pattern=rf"^{CB_CHECK}"))
    application.add_handler(CallbackQueryHandler(approve_execution, pattern=rf"^{CB_APPROVE}"))
    application.add_handler(CallbackQueryHandler(ignore_execution, pattern=rf"^{CB_IGNORE}"))
    application.add_handler(CallbackQueryHandler(reply_to_agent, pattern=rf"^{CB_REPLY}"))
    application.add_handler(CallbackQueryHandler(show_thread, pattern=rf"^{CB_THREAD}"))
    application.add_handler(CallbackQueryHandler(choose_parsed_option, pattern=rf"^{CB_OPT}"))
    application.add_handler(CallbackQueryHandler(choose_generic, pattern=rf"^{CB_GEN}"))
