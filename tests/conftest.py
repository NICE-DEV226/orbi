"""
Configuration de pytest pour les tests Orbi.
Définit les fixtures, marqueurs et configuration globale.
"""

import os
import sys
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

# Ajouter le répertoire src au Python path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Marqueurs personnalisés
pytest_plugins = []

def pytest_configure(config):
    """Configuration de pytest."""
    # Ajouter des marqueurs personnalisés
    config.addinivalue_line(
        "markers", "slow: marque les tests comme lents"
    )
    config.addinivalue_line(
        "markers", "integration: marque les tests d'intégration"
    )
    config.addinivalue_line(
        "markers", "unit: marque les tests unitaires"
    )
    config.addinivalue_line(
        "markers", "mongo: marque les tests nécessitant MongoDB"
    )
    config.addinivalue_line(
        "markers", "redis: marque les tests nécessitant Redis"
    )


MONGO_HELP = (
    "MongoDB de test injoignable ({uri}).\n"
    "Démarrez-en un : docker run -d --rm -p 127.0.0.1:27017:27017 mongo:7.0.45\n"
    "ou pointez MONGODB_TEST_URI vers une instance jetable (les données de test y sont créées puis supprimées)."
)


@pytest_asyncio.fixture(scope="session")
async def mongo_db():
    """Base MongoDB réelle, unique à la session, initialisée une seule fois avec Beanie."""
    from beanie import init_beanie
    from pymongo import AsyncMongoClient

    import src.core.database as database

    uri = os.environ.get("MONGODB_TEST_URI", "mongodb://127.0.0.1:27017")
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=3000)
    try:
        await client.admin.command("ping")
    except Exception:
        await client.close()
        pytest.exit(MONGO_HELP.format(uri=uri), returncode=2)

    db_name = f"orbi_test_{uuid.uuid4().hex[:12]}"
    database._database = client[db_name]
    await init_beanie(database=database._database, document_models=database._get_document_models())
    yield database._database
    await client.drop_database(db_name)
    await client.close()
    database._database = None


@pytest_asyncio.fixture(autouse=True)
async def setup_test_environment(monkeypatch, mongo_db):
    """Environnement isolé : variables de test, collections vidées, Redis simulé."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("MONGODB_DB", "orbi_test")

    import fakeredis

    import src.core.redis as redis_module
    from src.core.config import get_settings

    get_settings.cache_clear()

    for name in await mongo_db.list_collection_names():
        await mongo_db[name].delete_many({})

    fake_redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    redis_module._redis = fake_redis

    yield

    await fake_redis.aclose()
    redis_module._redis = None
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def aclient():
    """Client HTTP asynchrone sur la même boucle que la base (le client PyMongo async y est lié)."""
    from src.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        client.app = app  # type: ignore[attr-defined]
        yield client
