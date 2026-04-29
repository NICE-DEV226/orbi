"""
Orbi — Client Redis singleton avec pool de connexions.
Utilisé pour : sessions, cache, rate limiting, panier, file de notifications.
"""

import logging

import redis.asyncio as aioredis

from src.core.config import get_settings

logger = logging.getLogger("orbi.redis")

_redis: aioredis.Redis | None = None


async def init_redis() -> None:
    """Initialise le client Redis avec pool de connexions."""
    global _redis

    settings = get_settings()
    logger.info("Connexion à Redis: %s", settings.REDIS_URL)

    _redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )

    # Test de connectivité
    await _redis.ping()
    logger.info("Redis connecté et prêt")


async def close_redis() -> None:
    """Ferme proprement la connexion Redis."""
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("Connexion Redis fermée")


def get_redis() -> aioredis.Redis:
    """Retourne le client Redis singleton."""
    if _redis is None:
        raise RuntimeError("Redis n'est pas initialisé. Appelez init_redis() d'abord.")
    return _redis


# ── Utilitaires cache ──

async def cache_get(key: str) -> str | None:
    """Récupère une valeur du cache Redis."""
    return await get_redis().get(key)


async def cache_set(key: str, value: str, ttl_seconds: int = 300) -> None:
    """Stocke une valeur dans le cache Redis avec TTL."""
    await get_redis().set(key, value, ex=ttl_seconds)


async def cache_delete(key: str) -> None:
    """Supprime une clé du cache Redis."""
    await get_redis().delete(key)
