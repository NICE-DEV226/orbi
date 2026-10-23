"""
Orbi — Script d'initialisation de la Base de Données (Phase 10).
Crée le compte superadmin initial basé sur ADMIN_CHAT_ID.
"""

import asyncio
import logging

from src.core.config import get_settings
from src.core.database import init_db
from src.models.user import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orbi.init")

async def init() -> None:
    """Initialise la base de données Beanie et crée l'admin de base."""
    logger.info("Connexion à MongoDB...")
    await init_db()

    settings = get_settings()
    if not settings.ADMIN_CHAT_ID:
        logger.warning("Aucun ADMIN_CHAT_ID défini dans .env, l'admin n'a pas pu être créé de force.")
        return

    admin_id = settings.ADMIN_CHAT_ID
    logger.info("Vérification de l'administrateur principal (Telegram ID: %d)", admin_id)

    admin_user = await User.find_one(User.telegram_id == admin_id)

    if not admin_user:
        logger.info("Création de l'utilisateur Admin System...")
        admin_user = User(
            telegram_id=admin_id,
            username="system_admin",
            first_name="Admin",
            language="fr",
            role="superadmin"
        )
        await admin_user.insert()
        logger.info("✅ Administrateur créé avec succès.")
    else:
        if admin_user.role != "superadmin":
            logger.info("Mise à jour du rôle de l'utilisateur existant en superadmin...")
            admin_user.role = "superadmin"
            await admin_user.save()
            logger.info("✅ Rôle administrateur forcé avec succès.")
        else:
            logger.info("✅ Administrateur principal déjà en place.")

if __name__ == "__main__":
    asyncio.run(init())
