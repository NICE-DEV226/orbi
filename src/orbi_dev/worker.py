"""
Orbi Dev — Boucle de suivi des exécutions, indépendante du bot Telegram.

Un verrou Redis (SET NX EX) évite que plusieurs instances interrogent le fournisseur en même temps.
Le verrou n'est qu'une optimisation : les transitions atomiques garantissent déjà qu'un double
passage reste sans effet incorrect.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable

from telegram import Bot

from src.core.config import get_settings
from src.core.redis import get_redis
from src.orbi_dev.cards import update_cards
from src.orbi_dev.notifier import notify_pending
from src.orbi_dev.runner import refresh_active_executions

logger = logging.getLogger("orbi.dev.worker")

LOCK_KEY = "orbi_dev:refresh_lock"


BotProvider = Callable[[], Bot | None]


async def run_once(bot: Bot | None = None) -> int | None:
    """Un passage (suivi, puis annonces Telegram si le bot est prêt). Retourne None si une autre instance détient le verrou."""
    interval = get_settings().ORBI_DEV_REFRESH_INTERVAL
    acquired = await get_redis().set(LOCK_KEY, "1", nx=True, ex=max(interval - 1, 1))
    if not acquired:
        return None
    processed = await refresh_active_executions()
    if bot is not None:
        await update_cards(bot)
        await notify_pending(bot)
    return processed


async def run_forever(bot_provider: BotProvider = lambda: None) -> None:
    interval = get_settings().ORBI_DEV_REFRESH_INTERVAL
    logger.info("Suivi Orbi Dev démarré (intervalle %ss)", interval)
    while True:
        try:
            await run_once(bot_provider())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Passage de suivi Orbi Dev en échec")
        await asyncio.sleep(interval)


def start_worker(bot_provider: BotProvider = lambda: None) -> asyncio.Task | None:
    if get_settings().ORBI_DEV_REFRESH_INTERVAL <= 0:
        logger.info("Suivi Orbi Dev désactivé (ORBI_DEV_REFRESH_INTERVAL=0)")
        return None
    return asyncio.create_task(run_forever(bot_provider), name="orbi-dev-worker")


async def stop_worker(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
