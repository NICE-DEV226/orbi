"""
Tests pour les middlewares du bot Telegram.
Auth, i18n, rate limiting et logging — avec MongoDB et Redis simulés (voir conftest).
"""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram import User as TgUser
from telegram.ext import ContextTypes

from src.bot.middlewares.auth import AuthMiddleware
from src.bot.middlewares.i18n import I18nMiddleware
from src.bot.middlewares.logging_mw import LoggingMiddleware
from src.bot.middlewares.rate_limit import RateLimitMiddleware
from src.models.user import User as UserModel
from src.models.user import UserRole

TG_ID = 123456789


@pytest.fixture
def mock_update():
    """Update Telegram minimal : un message texte d'un utilisateur."""
    update = MagicMock(spec=Update)
    user = MagicMock(spec=TgUser)
    user.id = TG_ID
    user.username = "test_user"
    user.first_name = "Test"
    user.last_name = None
    user.language_code = "fr"
    update.effective_user = user
    update.callback_query = None
    update.my_chat_member = None
    update.message = MagicMock()
    update.message.text = "test message"
    update.message.date = datetime.now(UTC)
    update.effective_message = update.message
    update.effective_message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {}
    context.bot_data = {}
    return context


async def _make_user(**kwargs) -> UserModel:
    data = {"telegram_id": TG_ID, "username": "test_user", "first_name": "Test", "language": "fr"}
    user = UserModel(**{**data, **kwargs})
    await user.insert()
    return user


class TestAuthMiddleware:
    async def test_new_user_is_created(self, mock_update, mock_context):
        assert await AuthMiddleware()(mock_update, mock_context) is True

        stored = await UserModel.find_one(UserModel.telegram_id == TG_ID)
        assert stored is not None
        assert stored.language is None  # la langue est choisie explicitement plus tard
        assert mock_context.user_data["db_user"].telegram_id == TG_ID

    async def test_existing_user_is_loaded_not_duplicated(self, mock_update, mock_context):
        await _make_user(role=UserRole.ADMIN)

        assert await AuthMiddleware()(mock_update, mock_context) is True

        assert mock_context.user_data["db_user"].role == UserRole.ADMIN
        assert await UserModel.find(UserModel.telegram_id == TG_ID).count() == 1

    async def test_banned_user_is_blocked_and_notified(self, mock_update, mock_context):
        await _make_user(is_banned=True, ban_reason="Spam")
        middleware = AuthMiddleware()

        with patch.object(middleware, "_send_ban_message", new=AsyncMock()) as send:
            assert await middleware(mock_update, mock_context) is False

        send.assert_awaited_once()

    async def test_update_without_user_is_allowed(self, mock_context):
        update = MagicMock(spec=Update)
        update.effective_user = None

        assert await AuthMiddleware()(update, mock_context) is True


class TestI18nMiddleware:
    async def test_uses_language_of_db_user(self, mock_update, mock_context):
        mock_context.user_data["db_user"] = UserModel(telegram_id=TG_ID, first_name="T", language="en")

        await I18nMiddleware()(mock_update, mock_context)

        assert mock_context.user_data["lang"] == "en"

    async def test_falls_back_to_french_without_language(self, mock_update, mock_context):
        mock_context.user_data["db_user"] = UserModel(telegram_id=TG_ID, first_name="T")

        await I18nMiddleware()(mock_update, mock_context)

        assert mock_context.user_data["lang"] == "fr"

    async def test_translate_function_is_injected(self, mock_update, mock_context):
        mock_context.user_data["db_user"] = UserModel(telegram_id=TG_ID, first_name="T", language="fr")

        with patch("src.bot.middlewares.i18n.translate", return_value="Texte traduit") as translate:
            await I18nMiddleware()(mock_update, mock_context)
            assert mock_context.user_data["t"]("some.key") == "Texte traduit"

        translate.assert_called_once_with("some.key", "fr")

    async def test_update_without_user_is_ignored(self, mock_context):
        update = MagicMock(spec=Update)
        update.effective_user = None

        await I18nMiddleware()(update, mock_context)

        assert "lang" not in mock_context.user_data


class TestRateLimitMiddleware:
    async def test_requests_under_the_limit_are_allowed(self, mock_update, mock_context):
        middleware = RateLimitMiddleware(max_requests=3, window_seconds=60)

        for _ in range(3):
            assert await middleware(mock_update, mock_context) is True

    async def test_request_over_the_limit_is_blocked_and_user_notified(self, mock_update, mock_context):
        middleware = RateLimitMiddleware(max_requests=3, window_seconds=60)
        for _ in range(3):
            await middleware(mock_update, mock_context)

        assert await middleware(mock_update, mock_context) is False

        mock_update.effective_message.reply_text.assert_awaited_once()

    async def test_limit_is_per_user(self, mock_update, mock_context):
        middleware = RateLimitMiddleware(max_requests=1, window_seconds=60)
        await middleware(mock_update, mock_context)
        assert await middleware(mock_update, mock_context) is False

        mock_update.effective_user.id = TG_ID + 1
        assert await middleware(mock_update, mock_context) is True

    async def test_redis_failure_is_fail_open(self, mock_update, mock_context):
        middleware = RateLimitMiddleware(max_requests=1, window_seconds=60)

        with patch("src.bot.middlewares.rate_limit.get_redis", side_effect=RuntimeError("redis down")):
            assert await middleware(mock_update, mock_context) is True


class TestLoggingMiddleware:
    async def test_logs_user_and_message(self, mock_update, mock_context, caplog):
        with caplog.at_level(logging.INFO):
            await LoggingMiddleware()(mock_update, mock_context)

        assert str(TG_ID) in caplog.text
        assert "test message" in caplog.text
        assert "_request_start" in mock_context.user_data


class TestMiddlewareChain:
    async def test_chain_success_populates_context(self, mock_update, mock_context):
        await _make_user()

        await LoggingMiddleware()(mock_update, mock_context)
        assert await AuthMiddleware()(mock_update, mock_context) is True
        await I18nMiddleware()(mock_update, mock_context)
        assert await RateLimitMiddleware()(mock_update, mock_context) is True

        assert "db_user" in mock_context.user_data
        assert mock_context.user_data["lang"] == "fr"
        assert "t" in mock_context.user_data

    async def test_banned_user_stops_the_chain(self, mock_update, mock_context):
        await _make_user(is_banned=True, ban_reason="Spam")
        auth = AuthMiddleware()

        with patch.object(auth, "_send_ban_message", new=AsyncMock()):
            assert await auth(mock_update, mock_context) is False

        assert "lang" not in mock_context.user_data
