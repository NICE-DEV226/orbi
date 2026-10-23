"""Tests de sécurité P0 : auth API fail-closed, dev-login supprimé, webhook GitHub."""

import hashlib
import hmac

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.core.config import get_settings
from src.core.security import check_bearer
from src.services.developer_service import verify_github_signature


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    get_settings.cache_clear()
    from src.main import create_app

    yield TestClient(create_app())
    get_settings.cache_clear()


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
    def test_anonymous_is_refused(self, client, path):
        assert client.get(path).status_code in (401, 503)

    def test_wrong_token_is_refused(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_API_TOKEN", "good")
        get_settings.cache_clear()
        r = client.get("/api/v1/admin/users", headers={"Authorization": "Bearer bad"})
        assert r.status_code == 401


class TestDevLoginRemoved:
    def test_dev_login_route_is_gone(self, client):
        r = client.get("/admin/dev-login", follow_redirects=False)
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
