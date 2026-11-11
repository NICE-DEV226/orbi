"""
Orbi Dev — mode « conversation » : parler à l'agent comme à un chatbot (ADR-0010).

Contrairement au bouton « Répondre à l'agent » (une réponse, puis désarmé), le mode conversation est
persistant : tant qu'il est actif, chaque texte libre du propriétaire est transmis à l'exécution la plus
récemment active qui accepte les messages (capacité INTERACT). L'état vit dans Redis — il survit au
redémarrage du bot et reste lisible par le worker, qui pousse les nouvelles réponses de l'agent.

Le ciblage est dynamique : si l'agent courant se termine, le texte suivant part vers la prochaine
exécution active, sans rien reconfigurer. Les réponses ne sont poussées que pour les fournisseurs
déclarant HISTORY (lecture du fil) ; pour les autres, l'envoi fonctionne mais rien ne remonte.
"""

import asyncio
import hashlib
import json
import logging

from telegram import Bot
from telegram.constants import ChatAction, ParseMode

from src.core.redis import get_redis
from src.orbi_dev import runner, service
from src.orbi_dev.connectors.base import RemoteMessage
from src.orbi_dev.mdformat import to_telegram_html
from src.orbi_dev.models import ExecutionStatus

logger = logging.getLogger("orbi.dev.chat")

_PREFIX = "orbi_dev:chat:"
_ACTIVE_STATUSES = (ExecutionStatus.RUNNING, ExecutionStatus.NEEDS_ATTENTION)
_THREAD_LIMIT = 50
_MAX_PUSH_CHARS = 3800


def _typing_delay(text: str) -> float:
    """Pause « en train d'écrire » proportionnée à la longueur, plafonnée — jamais bloquante pour le worker."""
    return min(0.6 + len(text) / 500, 3.0)


async def _typing(bot: Bot, chat_id: int) -> None:
    """Montre « Orbi est en train d'écrire… » le temps d'une frappe humaine ; silencieux si ça échoue."""
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception:
        logger.debug("Action « typing » impossible", exc_info=True)


def _key(owner_id: int) -> str:
    return f"{_PREFIX}{owner_id}"


def _fingerprint(message: RemoteMessage) -> str:
    # Pas de timestamp : certains fournisseurs (et le fake) régénèrent `at` à chaque lecture.
    digest = hashlib.sha1(message.text.encode()).hexdigest()[:16]
    return f"{message.role}|{digest}"


async def is_enabled(owner_id: int) -> bool:
    """Le propriétaire a ouvert une discussion (bouton « Discuter ») et ne l'a pas quittée."""
    return bool(await get_redis().exists(_key(owner_id)))


async def enable(owner_id: int, *, execution_id: str | None = None, anchor: str | None = None) -> None:
    """Arme le mode conversation. `anchor` = empreinte du dernier message vu (évite le spam initial)."""
    state = {"anchor": anchor, "exec": execution_id}
    await get_redis().set(_key(owner_id), json.dumps(state))


async def disable(owner_id: int) -> None:
    await get_redis().delete(_key(owner_id))


async def _state(owner_id: int) -> dict:
    raw = await get_redis().get(_key(owner_id))
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


async def _save_state(owner_id: int, state: dict) -> None:
    await get_redis().set(_key(owner_id), json.dumps(state))


async def resolve_target(owner_id: int):
    """
    L'exécution à qui parler : la plus récemment active (RUNNING/NEEDS_ATTENTION, session chez le
    fournisseur, INTERACT vérifié côté interface) — triée par dernière activité, pas par création.
    """
    candidates = []
    for execution in await service.list_executions(owner_id, limit=50):
        if (
            execution.status in _ACTIVE_STATUSES
            and execution.external_id
            and await service.execution_interact_capable(owner_id, execution)
        ):
            candidates.append(execution)
    if not candidates:
        return None
    return max(candidates, key=lambda e: e.updated_at)


async def anchor_for(owner_id: int, execution_id: str | None) -> str | None:
    """Empreinte du dernier message du fil, pour ne pousser que ce qui arrive ensuite."""
    if not execution_id:
        return None
    try:
        messages = await runner.get_execution_thread(owner_id, execution_id, limit=_THREAD_LIMIT)
    except Exception:
        return None  # pas de HISTORY : la discussion reste utilisable en envoi seul
    return _fingerprint(messages[-1]) if messages else None


async def push_replies(bot: Bot | None) -> int:
    """
    Passage worker : pour chaque discussion ouverte, pousse les nouveaux messages de l'agent.

    L'agent est résolu à chaque passage (le plus récent actif) : si la conversation a changé de
    cible, le fil suivi suit. L'ancre empêche tout doublon ; sans ancre (provider sans HISTORY ou
    fil indisponible) on ne pousse rien plutôt que de risquer une avalanche de messages anciens.
    """
    if bot is None:
        return 0
    redis = get_redis()
    sent = 0
    async for key in redis.scan_iter(f"{_PREFIX}*"):
        try:
            owner_id = int(str(key).removeprefix(_PREFIX))
        except ValueError:
            continue
        try:
            sent += await _push_for_owner(bot, owner_id)
        except Exception:
            logger.exception("Remontée des réponses agent en échec (owner %s)", owner_id)
    return sent


async def _push_for_owner(bot: Bot, owner_id: int) -> int:
    state = await _state(owner_id)
    if not state:
        return 0
    execution = await resolve_target(owner_id)
    if execution is None:
        return 0
    if state.get("exec") != str(execution.id):
        # Nouvelle cible : on s'ancre sur le dernier message pour ne pas renvoyer l'historique.
        state = {"anchor": await anchor_for(owner_id, str(execution.id)), "exec": str(execution.id)}
        await _save_state(owner_id, state)
        return 0
    if not state.get("anchor"):
        return 0
    try:
        messages = await runner.get_execution_thread(owner_id, str(execution.id), limit=_THREAD_LIMIT)
    except Exception:
        return 0  # HISTORY indisponible ou fournisseur injoignable : on réessaiera au prochain passage

    anchor = state["anchor"]
    idx = next((i for i in range(len(messages) - 1, -1, -1) if _fingerprint(messages[i]) == anchor), None)
    if idx is None:
        # Historique tronqué ou ancre périmée : on ne renvoie que le tout dernier message agent.
        new_messages = [m for m in messages[-3:] if m.role == "agent"][-1:]
    else:
        new_messages = messages[idx + 1 :]

    delivered = 0
    for message in new_messages:
        if message.role != "agent" or not message.text.strip():
            continue
        text = message.text.strip()
        if len(text) > _MAX_PUSH_CHARS:
            text = text[:_MAX_PUSH_CHARS] + "…"
        stamp = f" ({message.at:%H:%M})" if message.at else ""
        await _typing(bot, owner_id)
        await asyncio.sleep(_typing_delay(text))
        await bot.send_message(
            chat_id=owner_id,
            text=f"💬 <b>Agent{stamp}</b>\n{to_telegram_html(text)}",
            parse_mode=ParseMode.HTML,
        )
        delivered += 1
    state["anchor"] = _fingerprint(messages[-1]) if messages else anchor
    await _save_state(owner_id, state)
    return delivered
