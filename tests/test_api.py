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


class TestWebhooks:
    """Tests pour les endpoints de webhooks."""
    
    def test_stripe_webhook_success(self, client):
        """Test le webhook Stripe avec signature valide."""
        mock_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"order_id": "ORD-2024-00001"},
                    "payment_status": "paid"
                }
            }
        }
        
        with patch('src.main.verify_stripe_webhook') as mock_verify, \
             patch('src.main.get_order') as mock_get_order, \
             patch('src.main.handle_payment_success') as mock_handle:
            
            mock_verify.return_value = mock_event
            mock_get_order.return_value = AsyncMock()
            mock_handle.return_value = AsyncMock()
            
            response = client.post(
                "/webhook/stripe",
                json=mock_event,
                headers={"stripe-signature": "valid_signature"}
            )
            
            assert response.status_code == 200
            assert response.json()["status"] == "success"
    
    def test_stripe_webhook_invalid_signature(self, client):
        """Test le webhook Stripe avec signature invalide."""
        with patch('src.main.verify_stripe_webhook') as mock_verify:
            mock_verify.return_value = None
            
            response = client.post(
                "/webhook/stripe",
                json={},
                headers={"stripe-signature": "invalid_signature"}
            )
            
            assert response.status_code == 200
            assert response.json()["status"] == "ignored"
    
    def test_orange_money_webhook(self, client):
        """Test le webhook Orange Money."""
        webhook_data = {
            "order_id": "ORD-2024-00001",
            "status": "SUCCESS"
        }
        
        with patch('src.main.get_order') as mock_get_order, \
             patch('src.main.handle_payment_success') as mock_handle:
            
            mock_order = AsyncMock()
            mock_order.order_id = "ORD-2024-00001"
            mock_get_order.return_value = mock_order
            mock_handle.return_value = AsyncMock()
            
            response = client.post("/webhook/orange-money", json=webhook_data)
            
            assert response.status_code == 200
            assert response.json()["status"] == "success"
    
    def test_wave_webhook(self, client):
        """Test le webhook Wave."""
        webhook_data = {
            "type": "checkout.session.completed",
            "data": {
                "client_reference": "ORD-2024-00001"
            }
        }
        
        with patch('src.main.get_order') as mock_get_order, \
             patch('src.main.handle_payment_success') as mock_handle:
            
            mock_order = AsyncMock()
            mock_order.order_id = "ORD-2024-00001"
            mock_get_order.return_value = mock_order
            mock_handle.return_value = AsyncMock()
            
            response = client.post("/webhook/wave", json=webhook_data)
            
            assert response.status_code == 200
            assert response.json()["status"] == "success"


class TestGitHubWebhook:
    """Tests pour le webhook GitHub."""
    
    def test_github_webhook_valid(self, client):
        """Test le webhook GitHub avec signature valide."""
        payload = {
            "action": "opened",
            "repository": {
                "name": "orbi",
                "full_name": "user/orbi"
            },
            "sender": {
                "login": "testuser"
            }
        }
        
        with patch('src.main.verify_github_signature') as mock_verify, \
             patch('src.main.process_github_webhook') as mock_process:
            
            mock_verify.return_value = True
            mock_process.return_value = AsyncMock()
            
            response = client.post(
                "/webhook/github",
                json=payload,
                headers={
                    "x-hub-signature-256": "valid_signature",
                    "x-github-event": "pull_request",
                    "x-github-delivery": "1234567890"
                }
            )
            
            assert response.status_code == 200
            assert response.json()["status"] == "accepted"
    
    def test_github_webhook_invalid_signature(self, client):
        """Test le webhook GitHub avec signature invalide."""
        with patch('src.main.verify_github_signature') as mock_verify:
            mock_verify.return_value = False
            
            response = client.post(
                "/webhook/github",
                json={},
                headers={"x-hub-signature-256": "invalid_signature"}
            )
            
            assert response.status_code == 200
            assert response.json()["status"] == "ignored"


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
