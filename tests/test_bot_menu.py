"""Bot Telegram : construction, menus sans bouton orphelin, modules supprimés absents."""

import re

import pytest
from telegram.ext import CommandHandler

from src.bot.app import create_bot_application
from src.bot.keyboards import main_menu_keyboard
from src.core.i18n import load_translations


@pytest.fixture
async def bot_app(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    from src.core.config import get_settings

    get_settings.cache_clear()
    load_translations()
    return await create_bot_application()


def _patterns(app) -> list[str]:
    found = []
    for handlers in app.handlers.values():
        for h in handlers:
            pattern = getattr(h, "pattern", None)
            if pattern is not None:
                found.append(pattern.pattern if hasattr(pattern, "pattern") else str(pattern))
    return found


def _commands(app) -> set[str]:
    return {c for hs in app.handlers.values() for h in hs if isinstance(h, CommandHandler) for c in h.commands}


class TestBotMenus:
    async def test_every_main_menu_button_has_a_handler(self, bot_app):
        patterns = _patterns(bot_app)
        callbacks = [b.callback_data for row in main_menu_keyboard("fr").inline_keyboard for b in row]
        assert [c for c in callbacks if not any(re.search(p, c) for p in patterns)] == []

    async def test_no_shop_or_checkout_handler(self, bot_app):
        assert [p for p in _patterns(bot_app) if re.search(r"shop|checkout|^\^pay|cart", p)] == []

    async def test_developer_menu_buttons_all_have_handlers(self, bot_app, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock

        import src.handlers.menu as menu

        captured = {}

        async def capture(update, context, text, keyboard):
            captured["keyboard"] = keyboard

        monkeypatch.setattr(menu, "send_or_edit_menu", capture)
        update = MagicMock()
        update.callback_query.answer = AsyncMock()
        context = MagicMock()
        context.user_data = {"lang": "fr"}

        await menu.show_developers_menu(update, context)

        callbacks = [b.callback_data for row in captured["keyboard"].inline_keyboard for b in row if b.callback_data]
        patterns = _patterns(bot_app)
        orphans = [c for c in callbacks if c != "nav:home" and not any(re.search(p, c) for p in patterns)]
        assert orphans == []

    async def test_debug_and_demo_commands_are_gone(self, bot_app):
        assert not ({"test", "ping"} & _commands(bot_app))


class TestAdminPanel:
    async def test_panel_only_offers_working_actions(self, bot_app):
        from unittest.mock import AsyncMock, MagicMock

        from src.handlers.admin_auth import show_admin_panel
        from src.models.user import User

        admin = User(telegram_id=1, first_name="Root", role="superadmin")
        update = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"db_user": admin, "lang": "fr"}

        await show_admin_panel(update, context)

        keyboard = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
        callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
        patterns = _patterns(bot_app)
        assert [c for c in callbacks if not any(re.search(p, c) for p in patterns)] == []
        assert not {"admin:users", "admin:tickets", "admin:config", "admin:broadcast"} & set(callbacks)

    async def test_stats_use_real_numbers(self, bot_app):
        from unittest.mock import AsyncMock, MagicMock

        from src.handlers.admin_auth import show_admin_stats
        from src.models.user import User

        admin = await User(telegram_id=1, first_name="Root", role="admin").insert()
        await User(telegram_id=2, first_name="Banni", is_banned=True).insert()
        update = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        context = MagicMock()
        context.user_data = {"db_user": admin, "lang": "fr"}

        await show_admin_stats(update, context)

        text = update.callback_query.edit_message_text.call_args.args[0]
        assert "Total : `2`" in text and "Bannis : `1`" in text
        for invented in ("99.9%", "45ms", "256MB"):
            assert invented not in text
