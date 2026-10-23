"""
Tests d'intégration pour l'API FastAPI.
Test les endpoints, webhooks et fonctionnalités REST.
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from src.main import create_app


@pytest.fixture
def client():
    """Fixture pour le client de test FastAPI."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_bot():
    """Mock du bot Telegram pour les tests."""
    bot = AsyncMock()
    bot.bot = AsyncMock()
    return bot


class TestHealthEndpoint:
    """Tests pour l'endpoint de health check."""
    
    def test_health_check_success(self, client):
        """Test le health check quand tout va bien."""
        # Mock des services pour qu'ils répondent correctement
        with patch('src.main.get_database') as mock_db, \
             patch('src.main.get_redis') as mock_redis:
            
            mock_db.return_value.command.return_value = {'ok': 1}
            mock_redis.return_value.ping.return_value = asyncio.Future()
            mock_redis.return_value.ping.return_value.set_result(True)
            
            response = client.get("/health")
            assert response.status_code == 200
            
            data = response.json()
            assert data["status"] == "ok"
            assert "services" in data
            assert data["services"]["mongodb"] == "ok"
            assert data["services"]["redis"] == "ok"
    
    def test_health_check_degraded(self, client):
        """Test le health check quand un service est down."""
        with patch('src.main.get_database') as mock_db, \
             patch('src.main.get_redis') as mock_redis:
            
            # MongoDB OK mais Redis KO
            mock_db.return_value.command.return_value = {'ok': 1}
            mock_redis.return_value.ping.side_effect = Exception("Redis down")
            
            response = client.get("/health")
            assert response.status_code == 503
            
            data = response.json()
            assert data["status"] == "degraded"
            assert data["services"]["mongodb"] == "ok"
            assert "error" in data["services"]["redis"]


class TestAPIEndpoints:
    """Tests pour les endpoints API."""
    
    def test_docs_available(self, client):
        """Test que la documentation Swagger est disponible."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_redoc_available(self, client):
        """Test que la documentation ReDoc est disponible."""
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_admin_endpoints_exist(self, client):
        """Test que les endpoints admin existent."""
        # Test avec auth mockée
        with patch('src.api.admin.verify_admin_token') as mock_auth:
            mock_auth.return_value = {"user_id": 1, "role": "admin"}
            
            response = client.get("/api/v1/admin/users")
            # Devrait retourner 200 ou 401 selon l'implémentation
            assert response.status_code in [200, 401, 403]
    
    def test_dev_endpoints_exist(self, client):
        """Test que les endpoints dev existent."""
        with patch('src.api.dev.verify_dev_token') as mock_auth:
            mock_auth.return_value = {"role": "developer"}
            
            response = client.get("/api/v1/dev/health/stats")
            # Devrait retourner 200 ou 401 selon l'implémentation
            assert response.status_code in [200, 401, 403]


class TestWebAuth:
    """Tests pour l'authentification web."""
    
    def test_web_auth_endpoints_exist(self, client):
        """Test que les endpoints d'auth web existent."""
        # Test login endpoint
        response = client.post("/admin/login", data={"username": "test", "password": "test"})
        # Devrait retourner 200, 401 ou 422 selon l'implémentation
        assert response.status_code in [200, 401, 422]
        
        # Test dashboard endpoint
        response = client.get("/admin/dashboard")
        # Devrait retourner 200 (si déjà auth) ou redirection
        assert response.status_code in [200, 302]


class TestErrorHandling:
    """Tests pour la gestion des erreurs."""
    
    def test_404_handling(self, client):
        """Test la gestion des 404."""
        response = client.get("/nonexistent")
        assert response.status_code == 404
    
    def test_method_not_allowed(self, client):
        """Test la gestion des méthodes non autorisées."""
        response = client.delete("/health")
        assert response.status_code == 405


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
