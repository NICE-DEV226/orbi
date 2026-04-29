"""
Configuration de pytest pour les tests Orbi.
Définit les fixtures, marqueurs et configuration globale.
"""

import pytest
import asyncio
import sys
import os
from pathlib import Path

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


@pytest.fixture(scope="session")
def event_loop():
    """Crée une boucle d'événements pour les tests async."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_test_environment():
    """Configuration automatique de l'environnement de test."""
    # Variables d'environnement pour les tests
    os.environ["ENVIRONMENT"] = "test"
    os.environ["MONGODB_DB"] = "orbi_test"
    os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # DB différente pour les tests
    
    yield
    
    # Nettoyage après les tests
    # Ici on pourrait nettoyer la base de données de test


@pytest.fixture
def mock_env_vars():
    """Fixture pour les variables d'environnement de test."""
    return {
        "ENVIRONMENT": "test",
        "MONGODB_DB": "orbi_test",
        "REDIS_URL": "redis://localhost:6379/15",
        "TELEGRAM_BOT_TOKEN": "test_token",
        "ADMIN_CHAT_ID": "123456789",
        "JWT_SECRET": "test_secret"
    }


# Configuration des collections de tests
collect_ignore_glob = [
    "*/__pycache__/*",
    "*/migrations/*"
]
