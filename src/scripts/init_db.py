"""
Orbi — Script d'initialisation de la Base de Données.
Crée le premier superadmin à partir de ADMIN_CHAT_ID, uniquement s'il n'existe encore aucun superadmin.
"""

import asyncio
import logging

from src.core.config import get_settings
from src.core.database import init_db
from src.models.user import User, UserRole

logger = logging.getLogger("orbi.init")

CONNECT_ATTEMPTS = 5


async def bootstrap_superadmin(admin_id: int) -> str:
    """
    Crée (ou promeut) ADMIN_CHAT_ID en superadmin si aucun superadmin n'existe.
    Retourne l'action effectuée : "skipped", "created" ou "promoted".
    Idempotent : un redémarrage ne modifie jamais les rôles existants.
    """
    if await User.find_one(User.role == UserRole.SUPERADMIN):
        return "skipped"

    user = await User.find_one(User.telegram_id == admin_id)
    if user is None:
        await User(
            telegram_id=admin_id,
            username="system_admin",
            first_name="Admin",
            language="fr",
            role=UserRole.SUPERADMIN,
        ).insert()
        return "created"

    user.role = UserRole.SUPERADMIN
    await user.save()
    return "promoted"


async def _connect_with_retry() -> None:
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        try:
            await init_db()
            return
        except Exception as e:
            if attempt == CONNECT_ATTEMPTS:
                raise
            delay = 2**attempt
            logger.warning("MongoDB indisponible (%s), nouvel essai dans %ds", type(e).__name__, delay)
            await asyncio.sleep(delay)


async def init() -> None:
    """Initialise Beanie et amorce le premier administrateur."""
    logging.basicConfig(level=logging.INFO)
    await _connect_with_retry()

    from src.orbi_dev.migrations import run_migrations

    await run_migrations()

    admin_id = get_settings().ADMIN_CHAT_ID
    if not admin_id:
        logger.warning("ADMIN_CHAT_ID non défini : aucun administrateur amorcé.")
        return

    action = await bootstrap_superadmin(admin_id)
    logger.info("Amorçage du superadmin : %s", action)


if __name__ == "__main__":
    asyncio.run(init())
