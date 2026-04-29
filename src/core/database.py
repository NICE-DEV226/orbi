"""
Orbi — Connexion MongoDB + initialisation Beanie ODM.
"""

import logging

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.core.config import get_settings

logger = logging.getLogger("orbi.database")

_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def init_db() -> None:
    """Initialise la connexion MongoDB et Beanie avec tous les modèles de documents."""
    global _client, _database

    settings = get_settings()
    logger.info("Connexion à MongoDB: %s / %s", settings.MONGODB_URI, settings.MONGODB_DB)

    _client = AsyncIOMotorClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    _database = _client[settings.MONGODB_DB]

    # Import dynamique des modèles Beanie — sera peuplé au fur et à mesure des phases
    document_models = _get_document_models()

    await init_beanie(
        database=_database,
        document_models=document_models,
    )
    logger.info("MongoDB + Beanie initialisés (%d modèles)", len(document_models))


def _get_document_models() -> list:
    """
    Retourne la liste de tous les modèles Beanie enregistrés.
    Point central d'enregistrement de tous les documents MongoDB.
    """
    from src.models.commerce import Order, Product, PromoCode
    from src.models.community import GroupConfig, KarmaLog, ModerationLog, Poll
    from src.models.developer import (
        ApiKey, 
        ApiRequestLog, 
        WebhookConfig, 
        WebhookDelivery,
        ApiLog,
        ErrorLog,
        GithubWebhookLog
    )
    from src.models.productivity import Note, Reminder, Task
    from src.models.ticket import Ticket
    from src.models.user import User

    return [
        User,
        Ticket,
        Product,
        Order,
        PromoCode,
        Poll,
        KarmaLog,
        ModerationLog,
        GroupConfig,
        Task,
        Reminder,
        Note,
        ApiKey,
        WebhookConfig,
        WebhookDelivery,
        ApiRequestLog,
        ApiLog,
        ErrorLog,
        GithubWebhookLog,
    ]


async def close_db() -> None:
    """Ferme proprement la connexion MongoDB."""
    global _client, _database
    if _client:
        _client.close()
        _client = None
        _database = None
        logger.info("Connexion MongoDB fermée")


def get_database() -> AsyncIOMotorDatabase:
    """Retourne l'instance de la base de données."""
    if _database is None:
        raise RuntimeError("La base de données n'est pas initialisée. Appelez init_db() d'abord.")
    return _database
