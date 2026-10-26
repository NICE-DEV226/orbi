"""Le module Communauté est optionnel (ENABLE_COMMUNITY) et désactivé par défaut."""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.ext import CommandHandler, MessageHandler

from src.bot.app import create_bot_application
from src.bot.keyboards import main_menu_keyboard
from src.core.config import get_settings
from src.core.i18n import load_translations
from src.models.user import NotificationPreferences, User


def _configure(monkeypatch, enabled: bool):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("ENABLE_COMMUNITY", "true" if enabled else "false")
    get_settings.cache_clear()
    load_translations()


def _handlers(app):
    return [h for hs in app.handlers.values() for h in hs]


def _patterns(app) -> list[str]:
    out = []
    for h in _handlers(app):
        pattern = getattr(h, "pattern", None)
        if pattern is not None:
            out.append(pattern.pattern if hasattr(pattern, "pattern") else str(pattern))
    return out


def _callbacks(keyboard) -> list[str]:
    return [b.callback_data for row in keyboard.inline_keyboard for b in row if b.callback_data]


def test_disabled_by_default():
    assert get_settings().ENABLE_COMMUNITY is False


class TestDisabled:
    async def test_menu_has_no_community_entry(self, monkeypatch):
        _configure(monkeypatch, False)
        callbacks = _callbacks(main_menu_keyboard("fr"))
        assert "mod:community" not in callbacks
        assert not {"group:add", "channel:add"} & set(callbacks)

    async def test_no_community_or_group_handler_is_registered(self, monkeypatch):
        _configure(monkeypatch, False)
        app = await create_bot_application()

        assert [p for p in _patterns(app) if re.search(r"community|group:|channel:|^\^mod:community", p)] == []
        commands = {c for h in _handlers(app) if isinstance(h, CommandHandler) for c in h.commands}
        assert not {"addgroup", "addchannel"} & commands

    async def test_group_messages_are_not_read(self, monkeypatch):
        """Garantie de confidentialité : sans le module, aucun handler ne modère le texte des groupes."""
        _configure(monkeypatch, False)
        app = await create_bot_application()
        names = {getattr(h.callback, "__name__", "") for h in _handlers(app) if isinstance(h, MessageHandler)}
        assert "handle_message_moderation" not in names

    async def test_every_visible_menu_button_has_a_handler(self, monkeypatch):
        _configure(monkeypatch, False)
        app = await create_bot_application()
        patterns = _patterns(app)
        assert [c for c in _callbacks(main_menu_keyboard("fr")) if not any(re.search(p, c) for p in patterns)] == []


class TestEnabled:
    async def test_menu_shows_the_module_and_group_shortcuts(self, monkeypatch):
        _configure(monkeypatch, True)
        callbacks = _callbacks(main_menu_keyboard("fr"))
        assert {"mod:community", "group:add", "channel:add"} <= set(callbacks)

    async def test_handlers_are_registered_and_cover_every_button(self, monkeypatch):
        _configure(monkeypatch, True)
        app = await create_bot_application()
        patterns = _patterns(app)
        assert [c for c in _callbacks(main_menu_keyboard("fr")) if not any(re.search(p, c) for p in patterns)] == []
        commands = {c for h in _handlers(app) if isinstance(h, CommandHandler) for c in h.commands}
        assert {"addgroup", "addchannel"} <= commands
        names = {getattr(h.callback, "__name__", "") for h in _handlers(app) if isinstance(h, MessageHandler)}
        assert "handle_message_moderation" in names

    async def test_community_submenu_buttons_have_handlers(self, monkeypatch):
        import src.handlers.menu as menu

        _configure(monkeypatch, True)
        app = await create_bot_application()
        captured = {}

        async def capture(update, context, text, keyboard):
            captured["keyboard"] = keyboard

        monkeypatch.setattr(menu, "send_or_edit_menu", capture)
        update = MagicMock()
        update.callback_query.answer = AsyncMock()
        context = MagicMock()
        context.user_data = {"lang": "fr"}

        await menu.show_community_menu(update, context)

        patterns = _patterns(app)
        orphans = [c for c in _callbacks(captured["keyboard"]) if c != "nav:home" and not any(re.search(p, c) for p in patterns)]
        assert orphans == []


class TestProfile:
    async def _notification_labels(self, monkeypatch, enabled: bool) -> str:
        from src.handlers.profile import show_notifications

        _configure(monkeypatch, enabled)
        user = User(telegram_id=1, first_name="A", language="fr")
        query = MagicMock()
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()
        context.user_data = {"db_user": user, "lang": "fr"}

        await show_notifications(update, context)

        markup = query.edit_message_text.call_args.kwargs["reply_markup"]
        return " ".join(b.text for row in markup.inline_keyboard for b in row)

    async def test_community_announcements_hidden_when_disabled(self, monkeypatch):
        assert "communauté" not in (await self._notification_labels(monkeypatch, False)).lower()

    async def test_community_announcements_listed_when_enabled(self, monkeypatch):
        assert "communauté" in (await self._notification_labels(monkeypatch, True)).lower()

    @pytest.mark.parametrize("enabled", [False, True])
    async def test_karma_only_shown_when_enabled(self, monkeypatch, enabled):
        from src.handlers.profile import _karma_line

        _configure(monkeypatch, enabled)
        user = User(telegram_id=1, first_name="A", karma_points=42)
        line = _karma_line("fr", user)
        assert ("42" in line) is enabled
        assert NotificationPreferences.COMMUNITY_ANNOUNCEMENTS == "community_announcements"
