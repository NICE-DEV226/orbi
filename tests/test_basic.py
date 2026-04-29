"""
Tests unitaires de base pour Orbi.
Couvre les modèles, services et fonctionnalités principales.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.models.user import User, UserRole
from src.models.ticket import Ticket, TicketStatus, TicketPriority, TicketCategory
from src.models.commerce import Product, Order, OrderStatus
from src.services.ticket_service import generate_ticket_id, create_ticket
from src.services.commerce_service import generate_order_id, get_catalog_page


@pytest.fixture
def mock_user():
    """Fixture pour un utilisateur de test."""
    return User(
        telegram_id=123456789,
        username="test_user",
        first_name="Test",
        language="fr",
        role=UserRole.USER
    )


@pytest.fixture
def mock_product():
    """Fixture pour un produit de test."""
    return Product(
        name_fr="Produit Test",
        name_en="Test Product",
        name_ar="منتج اختبار",
        description_fr="Description du produit test",
        price=99.99,
        stock=10,
        category="test",
        is_active=True
    )


class TestUserModel:
    """Tests pour le modèle User."""
    
    def test_user_creation(self, mock_user):
        """Test la création d'un utilisateur."""
        assert mock_user.telegram_id == 123456789
        assert mock_user.username == "test_user"
        assert mock_user.first_name == "Test"
        assert mock_user.language == "fr"
        assert mock_user.role == UserRole.USER
        assert not mock_user.is_banned
        assert not mock_user.is_admin
        assert not mock_user.is_superadmin
    
    def test_display_name(self, mock_user):
        """Test l'affichage du nom."""
        assert mock_user.display_name == "Test"
        
        # Test avec last_name
        mock_user.last_name = "User"
        assert mock_user.display_name == "Test User"
    
    def test_user_properties(self, mock_user):
        """Test les propriétés de l'utilisateur."""
        # Test rôle admin
        mock_user.role = UserRole.ADMIN
        assert mock_user.is_admin
        assert not mock_user.is_superadmin
        
        # Test rôle superadmin
        mock_user.role = UserRole.SUPERADMIN
        assert mock_user.is_admin
        assert mock_user.is_superadmin
    
    def test_touch_method(self, mock_user):
        """Test la méthode touch."""
        old_updated = mock_user.updated_at
        old_active = mock_user.last_active_at
        
        # Attendre un peu pour être sûr que le timestamp change
        asyncio.sleep(0.001)
        mock_user.touch()
        
        assert mock_user.updated_at > old_updated
        assert mock_user.last_active_at > old_active


class TestTicketModel:
    """Tests pour le modèle Ticket."""
    
    def test_ticket_creation(self):
        """Test la création d'un ticket."""
        ticket = Ticket(
            ticket_id="TKT-2024-00001",
            user_telegram_id=123456789,
            user_name="Test User",
            category=TicketCategory.TECHNICAL,
            subject="Problème technique",
            description="Mon bot ne répond pas"
        )
        
        assert ticket.ticket_id == "TKT-2024-00001"
        assert ticket.status == TicketStatus.OPEN
        assert ticket.priority == TicketPriority.MEDIUM
        assert ticket.category == TicketCategory.TECHNICAL
        assert not ticket.is_escalated
        assert not ticket.sla_breached
    
    def test_priority_detection(self):
        """Test la détection automatique de priorité."""
        # Test réclamation -> automatiquement Haute
        priority = Ticket.detect_priority(
            TicketCategory.COMPLAINT,
            "Service mauvais"
        )
        assert priority == TicketPriority.HIGH
        
        # Test mots-clés urgents
        priority = Ticket.detect_priority(
            TicketCategory.GENERAL,
            "paiement bloqué urgent",
            "fr"
        )
        assert priority == TicketPriority.URGENT
        
        # Test normal -> Moyenne
        priority = Ticket.detect_priority(
            TicketCategory.GENERAL,
            "question simple"
        )
        assert priority == TicketPriority.MEDIUM


class TestCommerceModels:
    """Tests pour les modèles Commerce."""
    
    def test_product_creation(self, mock_product):
        """Test la création d'un produit."""
        assert mock_product.name_fr == "Produit Test"
        assert mock_product.name_en == "Test Product"
        assert mock_product.name_ar == "منتج اختبار"
        assert mock_product.price == 99.99
        assert mock_product.stock == 10
        assert mock_product.is_available
    
    def test_product_availability(self, mock_product):
        """Test la disponibilité des produits."""
        # Produit disponible
        assert mock_product.is_available
        
        # Plus de stock
        mock_product.stock = 0
        assert not mock_product.is_available
        
        # Produit désactivé
        mock_product.stock = 5
        mock_product.is_active = False
        assert not mock_product.is_available
    
    def test_product_multilingual(self, mock_product):
        """Test les méthodes multilingues."""
        assert mock_product.get_name("fr") == "Produit Test"
        assert mock_product.get_name("en") == "Test Product"
        assert mock_product.get_name("ar") == "منتج اختبار"
        assert mock_product.get_name("es") == "Produit Test"  # fallback to fr
        
        assert mock_product.get_description("fr") == "Description du produit test"
    
    def test_order_creation(self):
        """Test la création d'une commande."""
        order = Order(
            order_id="ORD-2024-00001",
            user_telegram_id=123456789,
            user_name="Test User",
            items=[
                {
                    "product_id": "prod_1",
                    "name": "Produit Test",
                    "price": 99.99,
                    "quantity": 2
                }
            ],
            subtotal=199.98,
            total=199.98,
            currency="XOF"
        )
        
        assert order.order_id == "ORD-2024-00001"
        assert order.status == OrderStatus.PENDING_PAYMENT
        assert len(order.items) == 1
        assert order.subtotal == 199.98
        assert order.total == 199.98
    
    def test_order_status_history(self):
        """Test l'historique des statuts de commande."""
        order = Order(
            order_id="ORD-2024-00001",
            user_telegram_id=123456789,
            user_name="Test User"
        )
        
        # Ajouter un changement de statut
        order.add_status_change(OrderStatus.PAID, "Paiement reçu")
        
        assert order.status == OrderStatus.PAID
        assert len(order.status_history) == 1
        assert order.status_history[0]["status"] == "paid"
        assert order.status_history[0]["note"] == "Paiement reçu"


class TestTicketService:
    """Tests pour le service Ticket."""
    
    @pytest.mark.asyncio
    async def test_generate_ticket_id(self):
        """Test la génération d'ID de ticket."""
        ticket_id = await generate_ticket_id()
        
        # Vérifier le format TKT-YYYY-NNNNN
        assert ticket_id.startswith("TKT-")
        assert len(ticket_id) == 15  # TKT-YYYY-NNNNN
        
        # Vérifier que l'année est correcte
        current_year = datetime.now().strftime("%Y")
        assert current_year in ticket_id


class TestCommerceService:
    """Tests pour le service Commerce."""
    
    @pytest.mark.asyncio
    async def test_generate_order_id(self):
        """Test la génération d'ID de commande."""
        order_id = await generate_order_id()
        
        # Vérifier le format ORD-YYYY-NNNNN
        assert order_id.startswith("ORD-")
        assert len(order_id) == 15  # ORD-YYYY-NNNNN
        
        # Vérifier que l'année est correcte
        current_year = datetime.now().strftime("%Y")
        assert current_year in order_id
    
    @pytest.mark.asyncio
    async def test_get_catalog_page(self):
        """Test la pagination du catalogue."""
        # Mock du modèle Product
        mock_products = [
            Product(
                name_fr=f"Produit {i}",
                name_en=f"Product {i}",
                name_ar=f"منتج {i}",
                price=10.0 * i,
                stock=5,
                category="test",
                is_active=True
            ) for i in range(10)
        ]
        
        # Cette test nécessiterait une vraie base de données ou un mock plus complexe
        # Pour l'instant, on teste juste la structure
        products, total = await get_catalog_page(page=0)
        
        assert isinstance(products, list)
        assert isinstance(total, int)


class TestConfiguration:
    """Tests pour la configuration."""
    
    def test_config_structure(self):
        """Test que la configuration a la bonne structure."""
        from src.core.config import get_settings
        
        settings = get_settings()
        
        # Vérifier que les attributs existent
        assert hasattr(settings, 'ENVIRONMENT')
        assert hasattr(settings, 'TELEGRAM_BOT_TOKEN')
        assert hasattr(settings, 'MONGODB_URI')
        assert hasattr(settings, 'REDIS_URL')
        
        # Vérifier les propriétés
        assert hasattr(settings, 'is_production')
        assert hasattr(settings, 'is_development')
        assert hasattr(settings, 'use_webhook')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
