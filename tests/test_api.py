"""
Tests d'intégration de l'API FastAPI (MongoDB réel et Redis simulé, voir conftest).
Health check, docs, API protégées, authentification web et gestion d'erreurs.
"""

import re

import httpx

from src.core.config import get_settings
from src.main import create_app
from src.models.user import User


class TestHealthEndpoint:
    async def test_health_ok(self, aclient):
        response = await aclient.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "services": {"mongodb": "ok", "redis": "ok"}}

    async def test_health_degraded_without_leaking_details(self, aclient, monkeypatch):
        import src.core.redis as redis_module

        async def boom():
            raise ConnectionError("redis://secret-host:6379 is down")

        monkeypatch.setattr(redis_module._redis, "ping", boom)

        response = await aclient.get("/health")

        assert response.status_code == 503
        assert response.json()["services"] == {"mongodb": "ok", "redis": "error"}
        assert "secret-host" not in response.text


class TestDocs:
    async def test_docs_available_in_development(self, aclient):
        response = await aclient.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_redoc_available(self, aclient):
        assert (await aclient.get("/redoc")).status_code == 200

    async def test_docs_disabled_in_production(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("JWT_SECRET", "x" * 40)
        get_settings.cache_clear()

        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as prod_client:
            assert (await prod_client.get("/docs")).status_code == 404


class TestProtectedApi:
    async def test_admin_users_with_valid_token(self, aclient, monkeypatch):
        monkeypatch.setenv("ADMIN_API_TOKEN", "admin-token")
        get_settings.cache_clear()

        response = await aclient.get("/api/v1/admin/users", headers={"Authorization": "Bearer admin-token"})

        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_dev_token_does_not_open_admin_api(self, aclient, monkeypatch):
        monkeypatch.setenv("ADMIN_API_TOKEN", "admin-token")
        monkeypatch.setenv("DEV_API_TOKEN", "dev-token")
        get_settings.cache_clear()

        response = await aclient.get("/api/v1/admin/users", headers={"Authorization": "Bearer dev-token"})

        assert response.status_code == 401

    async def test_dev_stats_with_valid_token(self, aclient, monkeypatch):
        monkeypatch.setenv("DEV_API_TOKEN", "dev-token")
        get_settings.cache_clear()

        response = await aclient.get("/api/v1/dev/health/stats", headers={"Authorization": "Bearer dev-token"})

        assert response.status_code == 200


class TestWebAuth:
    async def test_login_page_is_public(self, aclient):
        assert (await aclient.get("/admin/login")).status_code == 200

    async def test_dashboard_requires_session(self, aclient):
        response = await aclient.get("/admin/")

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    async def test_magic_link_logs_in_admin(self, aclient):
        import src.core.redis as redis_module

        await User(telegram_id=42, first_name="Ada", role="admin").insert()
        await redis_module._redis.setex("magic_link:tok", 300, "42")

        response = await aclient.post("/admin/auth/tok")

        assert response.status_code == 303
        cookie = response.headers["set-cookie"]
        assert "admsession=" in cookie and "HttpOnly" in cookie
        assert await redis_module._redis.get("magic_link:tok") is None  # usage unique

    async def test_session_cookie_opens_dashboard(self, aclient):
        await User(telegram_id=42, first_name="Ada", role="admin").insert()
        import src.core.redis as redis_module

        await redis_module._redis.setex("magic_link:tok", 300, "42")
        await aclient.post("/admin/auth/tok")

        response = await aclient.get("/admin/")

        assert response.status_code == 200

    async def test_magic_link_refused_for_non_admin(self, aclient):
        import src.core.redis as redis_module

        await User(telegram_id=43, first_name="Bob", role="user").insert()
        await redis_module._redis.setex("magic_link:tok2", 300, "43")

        response = await aclient.post("/admin/auth/tok2")

        assert response.status_code == 403
        assert "admsession" not in response.headers.get("set-cookie", "")

    async def test_unknown_magic_link_is_refused(self, aclient):
        page = await aclient.get("/admin/auth/nope")
        assert page.status_code == 200 and "invalide ou expiré" in page.text and "Se connecter</button>" not in page.text

        response = await aclient.post("/admin/auth/nope")

        assert response.status_code == 400
        assert "admsession" not in response.headers.get("set-cookie", "")

    async def test_opening_the_link_does_not_use_it_up(self, aclient):
        """Les aperçus de lien de Telegram ouvrent la page avant l'utilisateur : un simple GET ne doit rien consommer."""
        import src.core.redis as redis_module

        await User(telegram_id=42, first_name="Ada", role="admin").insert()
        await redis_module._redis.setex("magic_link:tok", 300, "42")

        for _ in range(3):  # aperçu de Telegram, antivirus, double ouverture…
            page = await aclient.get("/admin/auth/tok")
            assert page.status_code == 200 and "admsession" not in page.headers.get("set-cookie", "")
            assert 'action="/admin/auth/tok"' in page.text and "Se connecter</button>" in page.text
            assert page.headers["cache-control"] == "no-store"
        assert await redis_module._redis.get("magic_link:tok") is not None

        assert (await aclient.post("/admin/auth/tok")).status_code == 303
        assert (await aclient.post("/admin/auth/tok")).status_code == 400  # usage unique

    async def test_two_simultaneous_clicks_cannot_both_log_in(self, aclient):
        import asyncio

        import src.core.redis as redis_module

        await User(telegram_id=42, first_name="Ada", role="admin").insert()
        await redis_module._redis.setex("magic_link:tok", 300, "42")

        results = await asyncio.gather(*(aclient.post("/admin/auth/tok") for _ in range(4)))

        assert sorted(r.status_code for r in results).count(303) == 1


class TestErrorHandling:
    async def test_404(self, aclient):
        assert (await aclient.get("/nonexistent")).status_code == 404

    async def test_method_not_allowed(self, aclient):
        assert (await aclient.delete("/health")).status_code == 405


class TestBotToDashboardLogin:
    async def test_link_sent_by_bot_logs_the_admin_in(self, aclient):
        """Le lien généré par le bot (/admin magic link) doit être accepté par la route web."""
        from unittest.mock import AsyncMock, MagicMock

        from src.handlers.admin_auth import request_magic_link

        admin = await User(telegram_id=77, first_name="Root", role="superadmin").insert()
        update = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.effective_chat.type = "private"
        context = MagicMock()
        context.user_data = {"db_user": admin, "lang": "fr"}

        await request_magic_link(update, context)

        text = update.callback_query.edit_message_text.call_args.args[0]
        login_url = re.search(r"https?://\S+/admin/auth/[0-9a-f-]+", text).group(0)
        path = "/" + login_url.split("/", 3)[3]

        response = await aclient.post(path)

        assert response.status_code == 303
        assert "admsession=" in response.headers["set-cookie"]


class TestMagicLinkMessage:
    URL = "https://orbi.example.org/admin/auth/0b0b0b0b-0000-0000-0000-000000000000"

    def test_link_is_always_in_a_copyable_block(self):
        from src.handlers.admin_auth import magic_link_text

        for clickable in (False, True):
            assert f"<code>{self.URL}</code>" in magic_link_text(self.URL, clickable=clickable)

    def test_localhost_link_is_not_offered_as_a_link_telegram_would_refuse(self):
        from src.handlers.admin_auth import magic_link_text

        text = magic_link_text("http://localhost:8000/admin/auth/abc", clickable=False)
        assert "<a " not in text and "<code>http://localhost:8000/admin/auth/abc</code>" in text

    def test_public_https_link_is_also_clickable(self):
        from src.handlers.admin_auth import magic_link_text

        assert f'<a href="{self.URL}">' in magic_link_text(self.URL, clickable=True)

    def test_base_url_cannot_inject_markup(self):
        from src.handlers.admin_auth import magic_link_text

        text = magic_link_text('https://x"><b>y</b>&z', clickable=True)
        assert "<b>y</b>" not in text and "&lt;b&gt;" in text


class TestMagicLinkMessageHasNoPreview:
    async def test_preview_is_disabled_on_the_message(self):
        from unittest.mock import AsyncMock, MagicMock

        from src.handlers.admin_auth import request_magic_link
        from src.models.user import User

        admin = await User(telegram_id=88, first_name="Root", role="superadmin").insert()
        update = MagicMock()
        update.callback_query = None
        update.effective_chat.type = "private"
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"db_user": admin, "lang": "fr"}

        await request_magic_link(update, context)

        assert update.effective_message.reply_text.call_args.kwargs["link_preview_options"].is_disabled is True
