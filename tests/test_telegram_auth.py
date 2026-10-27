"""Authentification par Mini App Telegram : validation d'initData, endpoint, cookies, en-têtes, accès depuis le bot."""

import json
import sys
import time
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlencode

import pytest

from src.core.config import get_settings
from src.models.user import User
from src.web.auth import COOKIE_NAME, safe_next
from src.web.telegram_auth import InvalidInitDataError, compute_hash, validate_init_data

BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

# Vecteur à réponse connue : signature confirmée par une bibliothèque indépendante (aiogram, check_webapp_signature).
KNOWN_INIT_DATA = (
    "auth_date=1700000000&query_id=AAHdF6IQAAAAAN0XohDhrOrc&user=%7B%22id%22%3A4242%2C%22first_name%22%3A%22Ada%22%2C"
    "%22last_name%22%3A%22Lovelace%22%2C%22username%22%3A%22ada%22%2C%22language_code%22%3A%22fr%22%7D"
    "&hash=7859e3d701d9a9976c3f08e631a1a08ac732f75d7e395e33a9ac0700112c3825"
)
KNOWN_NOW = 1700000100


def sign(user_id=4242, *, auth_date=None, token=BOT_TOKEN, extra=None) -> str:
    fields = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "AAH123",
        "user": json.dumps({"id": user_id, "first_name": "Ada"}, separators=(",", ":")),
        **(extra or {}),
    }
    fields["hash"] = compute_hash(fields, token)
    return urlencode(fields)


class TestValidator:
    def test_known_answer_vector(self):
        user = validate_init_data(KNOWN_INIT_DATA, BOT_TOKEN, now=KNOWN_NOW)
        assert (user.id, user.first_name, user.username) == (4242, "Ada", "ada")

    def test_wrong_bot_token_is_rejected(self):
        with pytest.raises(InvalidInitDataError, match="Signature"):
            validate_init_data(KNOWN_INIT_DATA, "999:other-token", now=KNOWN_NOW)

    @pytest.mark.parametrize("a,b", [("4242", "1")])
    def test_tampered_user_is_rejected(self, a, b):
        with pytest.raises(InvalidInitDataError, match="Signature"):
            validate_init_data(KNOWN_INIT_DATA.replace(a, b, 1), BOT_TOKEN, now=KNOWN_NOW)

    def test_extra_field_added_after_signing_is_rejected(self):
        with pytest.raises(InvalidInitDataError):
            validate_init_data(KNOWN_INIT_DATA + "&is_admin=true", BOT_TOKEN, now=KNOWN_NOW)

    def test_missing_hash(self):
        with pytest.raises(InvalidInitDataError, match="sans signature"):
            validate_init_data(KNOWN_INIT_DATA.split("&hash=")[0], BOT_TOKEN, now=KNOWN_NOW)

    def test_duplicate_field_is_rejected(self):
        with pytest.raises(InvalidInitDataError, match="dupliqué"):
            validate_init_data(KNOWN_INIT_DATA + "&auth_date=1", BOT_TOKEN, now=KNOWN_NOW)

    def test_stale_data_is_rejected(self):
        with pytest.raises(InvalidInitDataError, match="périmée"):
            validate_init_data(KNOWN_INIT_DATA, BOT_TOKEN, max_age=3600, now=1700000000 + 3601)

    def test_data_from_the_future_is_rejected(self):
        with pytest.raises(InvalidInitDataError, match="futur"):
            validate_init_data(sign(auth_date=int(time.time()) + 3600), BOT_TOKEN)

    @pytest.mark.parametrize("data", ["", "x" * 9000, "hash=abc", "user=%7B%7D&hash=00"])
    def test_garbage_is_rejected(self, data):
        with pytest.raises(InvalidInitDataError):
            validate_init_data(data, BOT_TOKEN)

    def test_missing_user_is_rejected_even_when_signed(self):
        fields = {"auth_date": str(int(time.time()))}
        fields["hash"] = compute_hash(fields, BOT_TOKEN)
        with pytest.raises(InvalidInitDataError, match="incomplète"):
            validate_init_data(urlencode(fields), BOT_TOKEN)

    def test_unconfigured_bot_token_never_validates(self):
        with pytest.raises(InvalidInitDataError, match="non configurée"):
            validate_init_data(sign(token=""), "")


class TestSafeNext:
    @pytest.mark.parametrize("value,expected", [
        ("/dev/executions/abc123", "/dev/executions/abc123"), ("/admin/users?q=a", "/admin/users?q=a"),
        ("//evil.example", "/dev/"), ("https://evil.example", "/dev/"), ("/dev/../etc", "/dev/"),
        ("javascript:alert(1)", "/dev/"), ("/other", "/dev/"), (None, "/dev/"), ("", "/dev/"),
    ])
    def test_only_internal_known_paths(self, value, expected):
        assert safe_next(value) == expected


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    get_settings.cache_clear()


async def login(aclient, init_data, **body):
    return await aclient.post("/admin/telegram-login", json={"initData": init_data, **body})


class TestLoginEndpoint:
    async def test_admin_gets_a_working_session(self, aclient, token):
        await User(telegram_id=4242, first_name="Ada", role="admin").insert()

        r = await login(aclient, sign())

        assert r.status_code == 200 and r.json() == {"ok": True, "redirect": "/dev/"}
        assert COOKIE_NAME in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
        assert (await aclient.get("/dev/")).status_code == 200  # le cookie ouvre bien l'interface

    async def test_redirect_follows_a_safe_next_only(self, aclient, token):
        await User(telegram_id=4242, first_name="Ada", role="superadmin").insert()
        assert (await login(aclient, sign(), next="/dev/projects")).json()["redirect"] == "/dev/projects"
        assert (await login(aclient, sign(), next="https://evil.example")).json()["redirect"] == "/dev/"

    async def test_non_admin_is_refused_without_session(self, aclient, token):
        await User(telegram_id=4242, first_name="Ada", role="user").insert()
        r = await login(aclient, sign())
        assert r.status_code == 403 and "set-cookie" not in r.headers

    async def test_banned_admin_is_refused(self, aclient, token):
        await User(telegram_id=4242, first_name="Ada", role="admin", is_banned=True).insert()
        assert (await login(aclient, sign())).status_code == 403

    async def test_unknown_account_is_told_to_open_the_bot_first(self, aclient, token):
        r = await login(aclient, sign())
        assert r.status_code == 403 and "/start" in r.json()["detail"]

    async def test_forged_or_stale_data_is_refused(self, aclient, token):
        await User(telegram_id=4242, first_name="Ada", role="admin").insert()
        assert (await login(aclient, sign(token="999:attacker"))).status_code == 401
        assert (await login(aclient, sign(auth_date=int(time.time()) - 86400))).status_code == 401
        r = await login(aclient, sign(user_id=1))  # signé pour un autre compte non administrateur : refusé aussi
        assert r.status_code in (401, 403)

    async def test_cannot_log_in_as_someone_else_by_editing_the_user_id(self, aclient, token):
        await User(telegram_id=1, first_name="Boss", role="superadmin").insert()
        await User(telegram_id=2, first_name="Mallory", role="user").insert()
        forged = sign(user_id=2).replace("%22id%22%3A2", "%22id%22%3A1")
        r = await login(aclient, forged)
        assert r.status_code == 401 and "set-cookie" not in r.headers

    async def test_not_configured_is_reported_not_silently_accepted(self, aclient, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
        get_settings.cache_clear()
        r = await login(aclient, sign(token="x"))
        assert r.status_code in (200, 401, 403, 503)  # jamais 500
        assert (await login(aclient, "")).status_code == 401

    async def test_oversized_payload_is_rejected_by_validation(self, aclient, token):
        assert (await login(aclient, "x" * 9000)).status_code == 422


class TestCookieAttributes:
    async def test_embedded_cookie_is_cross_site_capable_on_https(self, aclient, token, monkeypatch):
        """Telegram Web charge la Mini App dans une iframe : le cookie doit être SameSite=None; Secure; Partitioned."""
        monkeypatch.setenv("BASE_URL", "https://orbi.example.org")
        get_settings.cache_clear()
        await User(telegram_id=4242, first_name="Ada", role="admin").insert()

        cookie = (await login(aclient, sign())).headers["set-cookie"].lower()

        assert "samesite=none" in cookie and "secure" in cookie and "partitioned" in cookie

    async def test_plain_http_development_keeps_lax(self, aclient, token):
        await User(telegram_id=4242, first_name="Ada", role="admin").insert()
        cookie = (await login(aclient, sign())).headers["set-cookie"].lower()
        assert "samesite=lax" in cookie and "partitioned" not in cookie

    async def test_magic_link_cookie_stays_lax(self, aclient, token, monkeypatch):
        import src.core.redis as redis_module

        monkeypatch.setenv("BASE_URL", "https://orbi.example.org")
        get_settings.cache_clear()
        await User(telegram_id=7, first_name="A", role="admin").insert()
        await redis_module._redis.setex("magic_link:tk", 300, "7")

        cookie = (await aclient.post("/admin/auth/tk")).headers["set-cookie"].lower()

        assert "samesite=lax" in cookie


class TestPartitionedCookieOnOlderPython:
    """Python < 3.14 : Starlette lève une erreur sur `partitioned=True` ; l'attribut est ajouté à la main."""

    @pytest.mark.parametrize(
        "native",
        [
            pytest.param(
                True, marks=pytest.mark.skipif(sys.version_info < (3, 14), reason="Partitioned natif : Python 3.14+")
            ),
            False,
        ],
    )
    async def test_cookie_is_identical_whatever_the_python_version(self, aclient, token, monkeypatch, native):
        import src.web.auth as auth

        monkeypatch.setattr(auth, "_NATIVE_PARTITIONED", native)
        monkeypatch.setenv("BASE_URL", "https://orbi.example.org")
        get_settings.cache_clear()
        await User(telegram_id=4242, first_name="Ada", role="admin").insert()

        r = await login(aclient, sign())

        assert r.status_code == 200
        cookie = r.headers["set-cookie"].lower()
        assert cookie.count("partitioned") == 1 and "samesite=none" in cookie and "secure" in cookie


class TestPagesAndHeaders:
    async def test_login_redirect_keeps_the_target_page(self, aclient):
        r = await aclient.get("/dev/executions/abc")
        assert r.status_code == 303 and r.headers["location"] == "/admin/login?next=/dev/executions/abc"

    async def test_login_page_bootstraps_telegram_login_and_names_a_real_command(self, aclient):
        html = (await aclient.get("/admin/login?next=/dev/projects")).text
        assert "telegram-web-app.js" in html and "/admin/telegram-login" in html
        assert '"/dev/projects"' in html  # next repris côté page
        assert "<code>/web</code>" in html

    async def test_login_page_ignores_a_hostile_next(self, aclient):
        html = (await aclient.get("/admin/login", params={"next": "https://evil.example"})).text
        assert "evil.example" not in html

    async def test_frame_ancestors_allow_only_us_and_telegram(self, aclient):
        h = (await aclient.get("/livez")).headers
        assert "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org" in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff"

    async def test_dev_pages_load_the_mini_app_integration(self, aclient, token):
        await User(telegram_id=4242, first_name="Ada", role="admin").insert()
        await login(aclient, sign())
        html = (await aclient.get("/dev/")).text
        assert "telegram-web-app.js" in html and "tg.expand()" in html


def _context(user):
    context = MagicMock()
    context.user_data = {"db_user": user, "lang": "fr"}
    return context


def _update(chat_type: str = "private"):
    update = MagicMock()
    update.callback_query = None
    update.effective_chat.type = chat_type
    update.effective_message.reply_text = AsyncMock()
    return update


class TestBotEntryPoints:
    async def test_web_and_admin_commands_exist(self, monkeypatch):
        from telegram.ext import CommandHandler

        from src.bot.app import create_bot_application
        from src.core.i18n import load_translations

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
        get_settings.cache_clear()
        load_translations()
        app = await create_bot_application()
        commands = {c for hs in app.handlers.values() for h in hs if isinstance(h, CommandHandler) for c in h.commands}
        assert {"web", "admin"} <= commands

    async def test_web_command_sends_a_usable_link_even_on_http_localhost(self):
        from src.handlers.admin_auth import web_command

        admin = await User(telegram_id=1, first_name="Root", role="superadmin").insert()
        update = _update()

        await web_command(update, _context(admin))

        text = update.effective_message.reply_text.call_args.args[0]
        keyboard = update.effective_message.reply_text.call_args.kwargs["reply_markup"]
        assert "http://localhost:8000/admin/auth/" in text  # lien dans le texte
        assert all(b.url is None for row in keyboard.inline_keyboard for b in row)  # pas de bouton-lien http (refusé par Telegram)

    @pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
    async def test_magic_link_is_never_posted_in_a_group(self, chat_type):
        import src.core.redis as redis_module
        from src.handlers.admin_auth import web_command

        admin = await User(telegram_id=1, first_name="Root", role="superadmin").insert()
        update = _update(chat_type)

        await web_command(update, _context(admin))

        text = update.effective_message.reply_text.call_args.args[0]
        assert "/admin/auth/" not in text and "privé" in text
        assert [k async for k in redis_module._redis.scan_iter("magic_link:*")] == []  # aucun jeton même créé

    async def test_commands_are_registered_for_private_chats_only(self, monkeypatch):
        from telegram.ext import CommandHandler

        from src.bot.app import create_bot_application
        from src.core.i18n import load_translations

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
        get_settings.cache_clear()
        load_translations()
        app = await create_bot_application()
        handlers = [h for hs in app.handlers.values() for h in hs if isinstance(h, CommandHandler) and h.commands & {"web", "admin"}]
        assert len(handlers) == 2
        assert all("private" in repr(h.filters).lower() for h in handlers)

    async def test_web_command_is_refused_to_non_admins(self):
        from src.handlers.admin_auth import web_command

        update = _update()
        await web_command(update, _context(User(telegram_id=2, first_name="U")))
        assert "réservé" in update.effective_message.reply_text.call_args.args[0]

    async def test_mini_app_buttons_of_the_orbi_dev_home_only_on_https(self, monkeypatch):
        from cryptography.fernet import Fernet

        from src.handlers.dev_hub import build_home
        from src.orbi_dev import service

        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
        get_settings.cache_clear()
        await service.create_project(7, "demo", "https://github.com/acme/demo")
        await service.create_integration(7, "fake", "k")

        async def web_apps():
            _, markup = await build_home(7)
            return sorted(b.web_app.url for row in markup.inline_keyboard for b in row if b.web_app)

        assert await web_apps() == []  # BASE_URL http://localhost : Telegram refuserait
        monkeypatch.setenv("BASE_URL", "https://orbi.example.org")
        get_settings.cache_clear()
        assert await web_apps() == ["https://orbi.example.org/dev/", "https://orbi.example.org/dev/integrations"]

    async def test_admin_menu_has_an_administration_entry_non_admin_does_not(self):
        from src.bot.keyboards import main_menu_keyboard

        def callbacks(admin):
            return [b.callback_data for row in main_menu_keyboard("fr", is_admin=admin).inline_keyboard for b in row]

        assert "admin:panel" in callbacks(True) and "admin:panel" not in callbacks(False)

    async def test_menu_button_is_set_for_the_admin_chat_on_https(self, monkeypatch):
        from src.bot.app import configure_menu_button

        monkeypatch.setenv("BASE_URL", "https://orbi.example.org")
        monkeypatch.setenv("ADMIN_CHAT_ID", "4242")
        get_settings.cache_clear()
        app = MagicMock()
        app.bot.set_chat_menu_button = AsyncMock()

        await configure_menu_button(app)

        kwargs = app.bot.set_chat_menu_button.call_args.kwargs
        assert kwargs["chat_id"] == 4242 and kwargs["menu_button"].web_app.url == "https://orbi.example.org/dev/"

    async def test_menu_button_failure_never_blocks_start_and_http_does_nothing(self, monkeypatch):
        from src.bot.app import configure_menu_button

        app = MagicMock()
        app.bot.set_chat_menu_button = AsyncMock(side_effect=RuntimeError("boom"))
        await configure_menu_button(app)  # http : aucun appel
        app.bot.set_chat_menu_button.assert_not_awaited()

        monkeypatch.setenv("BASE_URL", "https://orbi.example.org")
        monkeypatch.setenv("ADMIN_CHAT_ID", "4242")
        get_settings.cache_clear()
        await configure_menu_button(app)  # erreur avalée
