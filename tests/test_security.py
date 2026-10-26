"""Tests de sécurité P0 : auth API fail-closed, dev-login supprimé, webhook GitHub."""

import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.core.config import get_settings
from src.core.security import check_bearer
from src.services.developer_service import verify_github_signature


class TestCheckBearer:
    def test_unconfigured_token_is_refused(self):
        with pytest.raises(HTTPException) as exc:
            check_bearer("Bearer anything", "")
        assert exc.value.status_code == 503

    @pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer wrong", "Basic secret", "secret"])
    def test_invalid_header_is_refused(self, header):
        with pytest.raises(HTTPException) as exc:
            check_bearer(header, "secret")
        assert exc.value.status_code == 401

    def test_valid_token_passes(self):
        check_bearer("Bearer secret", "secret")


class TestApiRoutesFailClosed:
    @pytest.mark.parametrize("path", ["/api/v1/admin/users", "/api/v1/admin/tickets", "/api/v1/dev/health/stats"])
    async def test_anonymous_is_refused(self, aclient, path):
        assert (await aclient.get(path)).status_code in (401, 503)

    async def test_wrong_token_is_refused(self, aclient, monkeypatch):
        monkeypatch.setenv("ADMIN_API_TOKEN", "good")
        get_settings.cache_clear()
        r = await aclient.get("/api/v1/admin/users", headers={"Authorization": "Bearer bad"})
        assert r.status_code == 401


class TestDevLoginRemoved:
    async def test_dev_login_route_is_gone(self, aclient):
        r = await aclient.get("/admin/dev-login", follow_redirects=False)
        assert r.status_code == 404
        assert "admsession" not in r.cookies


class TestGithubSignature:
    def test_missing_secret_refuses(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        get_settings.cache_clear()
        assert verify_github_signature(b"{}", "sha256=abc") is False

    def test_valid_and_invalid_signature(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
        get_settings.cache_clear()
        body = b'{"a":1}'
        good = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        assert verify_github_signature(body, good) is True
        assert verify_github_signature(body, "sha256=deadbeef") is False
        assert verify_github_signature(body, "") is False


class TestGithubWebhookRoute:
    def _sign(self, body: bytes, secret: str) -> str:
        return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    async def test_bad_signature_is_401_and_not_processed(self, aclient, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
        get_settings.cache_clear()
        with patch("src.services.developer_service.process_github_webhook", new=AsyncMock()) as proc:
            r = await aclient.post("/webhook/github", content=b"{}", headers={"x-hub-signature-256": "sha256=bad"})
        assert r.status_code == 401
        proc.assert_not_called()

    async def test_good_signature_is_processed(self, aclient, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
        get_settings.cache_clear()
        body = b'{"action":"opened"}'
        with patch("src.services.developer_service.process_github_webhook", new=AsyncMock()) as proc:
            r = await aclient.post(
                "/webhook/github",
                content=body,
                headers={"x-hub-signature-256": self._sign(body, "s3cret"), "x-github-event": "ping"},
            )
        assert r.status_code == 200
        proc.assert_called_once()


class TestTelegramWebhook:
    async def test_unavailable_without_secret_or_bot(self, aclient):
        assert (await aclient.post("/webhook/telegram", json={})).status_code == 503

    async def test_wrong_secret_is_401(self, aclient, monkeypatch):
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "tg-secret")
        get_settings.cache_clear()
        aclient.app.state.bot_app = AsyncMock()
        r = await aclient.post("/webhook/telegram", json={}, headers={"x-telegram-bot-api-secret-token": "nope"})
        assert r.status_code == 401
        aclient.app.state.bot_app.process_update.assert_not_called()


class TestProductionConfig:
    BASE = {"ENVIRONMENT": "production", "TELEGRAM_BOT_TOKEN": "t"}

    def _settings(self, monkeypatch, **env):
        for k, v in {**self.BASE, **env}.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        from src.core.config import Settings

        return Settings(_env_file=None)

    def test_default_jwt_secret_refused(self, monkeypatch):
        with pytest.raises(ValueError):
            self._settings(monkeypatch)

    def test_short_jwt_secret_refused(self, monkeypatch):
        with pytest.raises(ValueError):
            self._settings(monkeypatch, JWT_SECRET="short")

    def test_webhook_url_requires_secret(self, monkeypatch):
        with pytest.raises(ValueError):
            self._settings(monkeypatch, JWT_SECRET="x" * 40, TELEGRAM_WEBHOOK_URL="https://e.example")

    def test_valid_production_config(self, monkeypatch):
        s = self._settings(monkeypatch, JWT_SECRET="x" * 40)
        assert s.cookie_secure is True

    def test_development_cookie_not_secure(self, monkeypatch):
        s = self._settings(monkeypatch, ENVIRONMENT="development")
        assert s.cookie_secure is False


class TestWebHardening:
    async def test_logout_requires_post(self, aclient):
        assert (await aclient.get("/admin/logout", follow_redirects=False)).status_code == 405


class TestEmptyEnvValues:
    def test_blank_variables_fall_back_to_defaults(self, monkeypatch):
        """Un .env en cours de remplissage (ADMIN_CHAT_ID=, TELEGRAM_WEBHOOK_URL=) ne doit pas faire planter le démarrage."""
        from src.core.config import Settings

        monkeypatch.setenv("ADMIN_CHAT_ID", "")
        monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "")
        monkeypatch.setenv("ORBI_DEV_REFRESH_INTERVAL", "")

        settings = Settings(_env_file=None)

        assert settings.ADMIN_CHAT_ID == 0
        assert settings.TELEGRAM_WEBHOOK_URL == ""
        assert settings.ORBI_DEV_REFRESH_INTERVAL == 30

    def test_blank_bot_token_is_reported_as_missing(self, monkeypatch):
        from pydantic import ValidationError

        from src.core.config import Settings

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")

        with pytest.raises(ValidationError, match="TELEGRAM_BOT_TOKEN"):
            Settings(_env_file=None)
