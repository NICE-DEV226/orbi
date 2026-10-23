"""
Orbi Dev — Boucle de suivi des exécutions, indépendante du bot Telegram.

Un verrou Redis (SET NX EX) évite que plusieurs instances interrogent le fournisseur en même temps.
Le verrou n'est qu'une optimisation : les transitions atomiques garantissent déjà qu'un double
passage reste sans effet incorrect.
"""

import asyncio
import contextlib
import logging

from src.core.config import get_settings
from src.core.redis import get_redis
from src.orbi_dev.runner import refresh_active_executions

logger = logging.getLogger("orbi.dev.worker")

LOCK_KEY = "orbi_dev:refresh_lock"


async def run_once() -> int | None:
    """Un passage. Retourne None si une autre instance détient le verrou."""
    interval = get_settings().ORBI_DEV_REFRESH_INTERVAL
    acquired = await get_redis().set(LOCK_KEY, "1", nx=True, ex=max(interval - 1, 1))
    if not acquired:
        return None
    return await refresh_active_executions()


async def run_forever() -> None:
    interval = get_settings().ORBI_DEV_REFRESH_INTERVAL
    logger.info("Suivi Orbi Dev démarré (intervalle %ss)", interval)
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Passage de suivi Orbi Dev en échec")
        await asyncio.sleep(interval)


def start_worker() -> asyncio.Task | None:
    if get_settings().ORBI_DEV_REFRESH_INTERVAL <= 0:
        logger.info("Suivi Orbi Dev désactivé (ORBI_DEV_REFRESH_INTERVAL=0)")
        return None
    return asyncio.create_task(run_forever(), name="orbi-dev-worker")


async def stop_worker(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
