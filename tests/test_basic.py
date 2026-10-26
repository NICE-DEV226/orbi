"""
Tests unitaires de base pour Orbi.
Couvre les modèles, services et fonctionnalités principales.
"""

import asyncio
from datetime import datetime

import pytest

from src.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from src.models.user import User, UserRole
from src.services.ticket_service import generate_ticket_id


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


class TestTicketService:
    """Tests pour le service Ticket."""

    @pytest.mark.asyncio
    async def test_generate_ticket_id(self):
        """Test la génération d'ID de ticket."""
        ticket_id = await generate_ticket_id()

        # Vérifier le format TKT-YYYY-NNNNN
        assert ticket_id.startswith("TKT-")
        assert len(ticket_id) == 14  # TKT-YYYY-NNNNN

        # Vérifier que l'année est correcte
        current_year = datetime.now().strftime("%Y")
        assert current_year in ticket_id


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
