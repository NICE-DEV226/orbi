"""
Tests pour les middlewares du bot Telegram.
Test l'authentification, i18n, rate limiting et logging.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from telegram import Update, User
from telegram.ext import ContextTypes

from src.bot.middlewares.auth import AuthMiddleware
from src.bot.middlewares.i18n import I18nMiddleware
from src.bot.middlewares.rate_limit import RateLimitMiddleware
from src.bot.middlewares.logging_mw import LoggingMiddleware
from src.models.user import User as UserModel, UserRole


@pytest.fixture
def mock_update():
    """Mock pour un Update Telegram."""
    update = MagicMock(spec=Update)
    user = MagicMock(spec=User)
    user.id = 123456789
    user.username = "test_user"
    user.first_name = "Test"
    user.language_code = "fr"
    update.effective_user = user
    update.message = MagicMock()
    update.message.text = "test message"
    update.message.date = datetime.now(timezone.utc)
    return update


@pytest.fixture
def mock_context():
    """Mock pour un Context Telegram."""
    context = MagicMock(spec=ContextTypes)
    context.user_data = {}
    context.bot_data = {}
    return context


class TestAuthMiddleware:
    """Tests pour le middleware d'authentification."""
    
    @pytest.mark.asyncio
    async def test_auth_new_user_creation(self, mock_update, mock_context):
        """Test la création d'un nouvel utilisateur."""
        middleware = AuthMiddleware()
        
        with patch('src.models.user.User.find_one') as mock_find, \
             patch('src.models.user.User.insert') as mock_insert:
            
            # L'utilisateur n'existe pas encore
            mock_find.return_value = None
            
            # Créer l'utilisateur qui sera inséré
            new_user = UserModel(
                telegram_id=123456789,
                username="test_user",
                first_name="Test",
                language="fr"
            )
            mock_insert.return_value = new_user
            
            result = await middleware(mock_update, mock_context)
            
            # Vérifier que l'utilisateur a été créé
            assert result is True
            assert "db_user" in mock_context.user_data
            mock_find.assert_called_once()
            mock_insert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_auth_existing_user(self, mock_update, mock_context):
        """Test le chargement d'un utilisateur existant."""
        middleware = AuthMiddleware()
        
        existing_user = UserModel(
            telegram_id=123456789,
            username="test_user",
            first_name="Test",
            language="fr",
            role=UserRole.USER
        )
        
        with patch('src.models.user.User.find_one') as mock_find:
            mock_find.return_value = existing_user
            
            result = await middleware(mock_update, mock_context)
            
            assert result is True
            assert mock_context.user_data["db_user"] == existing_user
            mock_find.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_auth_banned_user(self, mock_update, mock_context):
        """Test le blocage d'un utilisateur banni."""
        middleware = AuthMiddleware()
        
        banned_user = UserModel(
            telegram_id=123456789,
            username="test_user",
            first_name="Test",
            language="fr",
            is_banned=True,
            ban_reason="Spam"
        )
        
        with patch('src.models.user.User.find_one') as mock_find, \
             patch.object(middleware, '_send_ban_message') as mock_send:
            
            mock_find.return_value = banned_user
            
            result = await middleware(mock_update, mock_context)
            
            assert result is False  # L'utilisateur est bloqué
            mock_send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_auth_no_user(self, mock_context):
        """Test le cas où il n'y a pas d'utilisateur (update système)."""
        middleware = AuthMiddleware()
        update = MagicMock(spec=Update)
        update.effective_user = None
        
        result = await middleware(update, mock_context)
        
        assert result is True  # Les updates système sont autorisés


class TestI18nMiddleware:
    """Tests pour le middleware d'internationalisation."""
    
    @pytest.mark.asyncio
    async def test_i18n_language_detection(self, mock_update, mock_context):
        """Test la détection de langue."""
        middleware = I18nMiddleware()
        
        # Simuler un utilisateur avec une langue en base
        db_user = UserModel(
            telegram_id=123456789,
            username="test_user",
            first_name="Test",
            language="en"
        )
        mock_context.user_data["db_user"] = db_user
        
        with patch('src.core.i18n.t') as mock_translate:
            mock_translate.return_value = "Translated text"
            
            await middleware(mock_update, mock_context)
            
            # Vérifier que la langue de l'utilisateur est utilisée
            assert mock_context.user_data.get("language") == "en"
    
    @pytest.mark.asyncio
    async def test_i18n_fallback_language(self, mock_update, mock_context):
        """Test le fallback vers la langue par défaut."""
        middleware = I18nMiddleware()
        
        # Utilisateur sans langue spécifiée
        db_user = UserModel(
            telegram_id=123456789,
            username="test_user",
            first_name="Test"
        )
        mock_context.user_data["db_user"] = db_user
        
        await middleware(mock_update, mock_context)
        
        # Devrait utiliser la langue par défaut (fr)
        assert mock_context.user_data.get("language") == "fr"
    
    @pytest.mark.asyncio
    async def test_i18n_translate_function(self, mock_update, mock_context):
        """Test que la fonction t() est disponible dans le contexte."""
        middleware = I18nMiddleware()
        
        db_user = UserModel(
            telegram_id=123456789,
            username="test_user",
            first_name="Test",
            language="fr"
        )
        mock_context.user_data["db_user"] = db_user
        
        with patch('src.core.i18n.t') as mock_translate:
            mock_translate.return_value = "Texte traduit"
            
            await middleware(mock_update, mock_context)
            
            # La fonction t() devrait être disponible
            assert "t" in mock_context.user_data


class TestRateLimitMiddleware:
    """Tests pour le middleware de rate limiting."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_allowed(self, mock_update, mock_context):
        """Test le cas où l'utilisateur est autorisé."""
        middleware = RateLimitMiddleware()
        
        with patch('src.core.redis.cache_get') as mock_get, \
             patch('src.core.redis.cache_set') as mock_set:
            
            # Pas de clé en cache = première requête
            mock_get.return_value = None
            
            result = await middleware(mock_update, mock_context)
            
            assert result is True
            mock_get.assert_called_once()
            mock_set.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rate_limit_blocked(self, mock_update, mock_context):
        """Test le cas où l'utilisateur est rate limited."""
        middleware = RateLimitMiddleware()
        
        with patch('src.core.redis.cache_get') as mock_get:
            # L'utilisateur a déjà fait trop de requêtes
            mock_get.return_value = "blocked"
            
            result = await middleware(mock_update, mock_context)
            
            assert result is False
            mock_get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rate_limit_increment(self, mock_update, mock_context):
        """Test l'incrémentation du compteur de requêtes."""
        middleware = RateLimitMiddleware()
        
        with patch('src.core.redis.cache_get') as mock_get, \
             patch('src.core.redis.cache_set') as mock_set:
            
            # L'utilisateur a fait quelques requêtes mais n'est pas bloqué
            mock_get.return_value = "5"  # Moins que la limite
            
            result = await middleware(mock_update, mock_context)
            
            assert result is True
            mock_get.assert_called_once()
            mock_set.assert_called_once()


class TestLoggingMiddleware:
    """Tests pour le middleware de logging."""
    
    @pytest.mark.asyncio
    async def test_logging_basic(self, mock_update, mock_context):
        """Test le logging de base."""
        middleware = LoggingMiddleware()
        
        with patch('logging.getLogger') as mock_logger:
            logger_instance = MagicMock()
            mock_logger.return_value = logger_instance
            
            await middleware(mock_update, mock_context)
            
            # Vérifier que le log a été écrit
            logger_instance.info.assert_called()
            
            # Vérifier les arguments du log
            call_args = logger_instance.info.call_args
            assert "user_id" in str(call_args)
            assert "123456789" in str(call_args)


class TestMiddlewareIntegration:
    """Tests d'intégration des middlewares."""
    
    @pytest.mark.asyncio
    async def test_middleware_chain_success(self, mock_update, mock_context):
        """Test la chaîne complète des middlewares avec succès."""
        auth_mw = AuthMiddleware()
        i18n_mw = I18nMiddleware()
        rate_limit_mw = RateLimitMiddleware()
        logging_mw = LoggingMiddleware()
        
        # Mock pour que tout se passe bien
        user = UserModel(
            telegram_id=123456789,
            username="test_user",
            first_name="Test",
            language="fr"
        )
        
        with patch('src.models.user.User.find_one', return_value=user), \
             patch('src.core.redis.cache_get', return_value=None), \
             patch('src.core.redis.cache_set'), \
             patch('logging.getLogger'):
            
            # Exécuter la chaîne de middlewares
            await logging_mw(mock_update, mock_context)
            auth_result = await auth_mw(mock_update, mock_context)
            assert auth_result is True
            
            await i18n_mw(mock_update, mock_context)
            rate_result = await rate_limit_mw(mock_update, mock_context)
            assert rate_result is True
            
            # Vérifier que le contexte est bien peuplé
            assert "db_user" in mock_context.user_data
            assert "language" in mock_context.user_data
            assert "t" in mock_context.user_data
    
    @pytest.mark.asyncio
    async def test_middleware_chain_auth_failure(self, mock_update, mock_context):
        """Test la chaîne avec échec d'authentification."""
        auth_mw = AuthMiddleware()
        logging_mw = LoggingMiddleware()
        
        # Utilisateur banni
        banned_user = UserModel(
            telegram_id=123456789,
            username="test_user",
            first_name="Test",
            is_banned=True,
            ban_reason="Spam"
        )
        
        with patch('src.models.user.User.find_one', return_value=banned_user), \
             patch.object(auth_mw, '_send_ban_message'), \
             patch('logging.getLogger'):
            
            await logging_mw(mock_update, mock_context)
            auth_result = await auth_mw(mock_update, mock_context)
            
            # L'authentification échoue
            assert auth_result is False
            
            # Les autres middlewares ne devraient pas s'exécuter
            assert "language" not in mock_context.user_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
