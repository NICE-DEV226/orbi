"""
Configuration de pytest pour les tests Orbi.
Définit les fixtures, marqueurs et configuration globale.
"""

import sys
from pathlib import Path

import pytest

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


@pytest.fixture(autouse=True)
async def setup_test_environment(monkeypatch):
    """Environnement isolé : variables de test, MongoDB simulé (Beanie) et Redis simulé."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("MONGODB_DB", "orbi_test")

    import fakeredis
    from beanie import init_beanie
    from mongomock_motor import AsyncMongoMockClient

    import src.core.database as database
    import src.core.redis as redis_module
    from src.core.config import get_settings

    get_settings.cache_clear()

    client = AsyncMongoMockClient()
    database._database = client["orbi_test"]
    await init_beanie(database=database._database, document_models=database._get_document_models())

    redis_module._redis = fakeredis.FakeAsyncRedis(decode_responses=True)

    yield

    await redis_module._redis.aclose()
    redis_module._redis = None
    database._database = None
    get_settings.cache_clear()
