"""Tests d'infrastructure : amorçage admin idempotent, liveness, métriques protégées."""

import httpx
import pytest

from src.core.config import get_settings
from src.main import create_app
from src.models.user import User, UserRole
from src.scripts.init_db import bootstrap_superadmin


@pytest.fixture
async def aclient():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestBootstrapSuperadmin:
    async def test_creates_superadmin_when_none_exists(self):
        assert await bootstrap_superadmin(111) == "created"

        user = await User.find_one(User.telegram_id == 111)
        assert user.role == UserRole.SUPERADMIN

    async def test_promotes_existing_user(self):
        await User(telegram_id=111, first_name="A").insert()

        assert await bootstrap_superadmin(111) == "promoted"

        assert (await User.find_one(User.telegram_id == 111)).role == UserRole.SUPERADMIN

    async def test_restart_does_not_reinstate_demoted_admin(self):
        await User(telegram_id=222, first_name="Boss", role=UserRole.SUPERADMIN).insert()
        await User(telegram_id=111, first_name="Old", role=UserRole.USER).insert()

        assert await bootstrap_superadmin(111) == "skipped"

        assert (await User.find_one(User.telegram_id == 111)).role == UserRole.USER


class TestLivenessAndMetrics:
    async def test_livez_has_no_dependencies(self, aclient, monkeypatch):
        import src.core.redis as redis_module

        monkeypatch.setattr(redis_module, "_redis", None)  # Redis "indisponible"

        response = await aclient.get("/livez")

        assert response.status_code == 200

    async def test_metrics_refused_without_token(self, aclient):
        assert (await aclient.get("/metrics")).status_code == 503

    async def test_metrics_refused_with_wrong_token(self, aclient, monkeypatch):
        monkeypatch.setenv("METRICS_API_TOKEN", "m-token")
        get_settings.cache_clear()

        response = await aclient.get("/metrics", headers={"Authorization": "Bearer nope"})

        assert response.status_code == 401

    async def test_metrics_exposes_route_templates(self, aclient, monkeypatch):
        monkeypatch.setenv("METRICS_API_TOKEN", "m-token")
        get_settings.cache_clear()
        await aclient.get("/health")
        await aclient.get("/does-not-exist-123")

        response = await aclient.get("/metrics", headers={"Authorization": "Bearer m-token"})

        assert response.status_code == 200
        assert 'route="/health"' in response.text
        assert "does-not-exist-123" not in response.text  # cardinalité bornée


class TestLifespanShutdown:
    async def test_failed_bot_start_does_not_cause_a_shutdown_error(self, caplog, monkeypatch):
        """Token invalide : le bot ne démarre pas, l'arrêt ne doit ni tenter de l'arrêter ni logguer d'erreur."""
        import logging
        from unittest.mock import AsyncMock

        import src.bot.app as bot_module
        import src.main as main_module

        monkeypatch.setenv("ORBI_DEV_REFRESH_INTERVAL", "0")
        get_settings.cache_clear()
        stop_bot = AsyncMock()
        monkeypatch.setattr(bot_module, "create_bot_application", AsyncMock(return_value=object()))
        monkeypatch.setattr(bot_module, "start_bot", AsyncMock(side_effect=RuntimeError("token rejected")))
        monkeypatch.setattr(bot_module, "stop_bot", stop_bot)
        for name in ("init_db", "init_redis", "close_redis", "close_db"):
            monkeypatch.setattr(main_module, name, AsyncMock())
        monkeypatch.setattr(main_module, "init_performance_optimizations", AsyncMock())
        monkeypatch.setattr(main_module, "cleanup_performance_optimizations", AsyncMock())

        with caplog.at_level(logging.ERROR):
            async with main_module.lifespan(main_module.create_app()):
                pass

        stop_bot.assert_not_awaited()
        assert "Erreur à l'arrêt" not in caplog.text
