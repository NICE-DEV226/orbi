"""Aucun bouton orphelin : chaque callback_data écrit dans le code a un handler enregistré (module Communauté activé)."""

import re
from pathlib import Path

import pytest
from telegram.ext import CallbackQueryHandler, ConversationHandler

from src.bot.app import create_bot_application
from src.core.config import get_settings
from src.core.i18n import load_translations

SRC = Path(__file__).resolve().parent.parent / "src"
CALLBACK = re.compile(r'callback_data\s*=\s*(f?)"([^"]+)"')
CONSTANT_USE = re.compile(r"callback_data\s*=\s*(CB_[A-Z_]+)\b")
CONSTANT = re.compile(r'^(CB_[A-Z_]+)\s*=\s*"([^"]+)"', re.M)


def _collect_patterns(handlers) -> list[str]:
    patterns = []
    for handler in handlers:
        if isinstance(handler, ConversationHandler):
            nested = list(handler.entry_points) + list(handler.fallbacks)
            for state_handlers in handler.states.values():
                nested += list(state_handlers)
            patterns += _collect_patterns(nested)
        elif isinstance(handler, CallbackQueryHandler) and handler.pattern is not None:
            patterns.append(handler.pattern.pattern if hasattr(handler.pattern, "pattern") else str(handler.pattern))
    return patterns


def _literal_callbacks() -> dict[str, str]:
    """callback_data réellement utilisés par des boutons (littéraux, f-strings instanciés, constantes CB_*)."""
    constants = dict(CONSTANT.findall((SRC / "bot" / "keyboards.py").read_text(encoding="utf-8")))
    found: dict[str, str] = {}
    for path in list((SRC / "handlers").glob("*.py")) + [SRC / "bot" / "keyboards.py"]:
        text = path.read_text(encoding="utf-8")
        origin = str(path.relative_to(SRC.parent))
        for is_f, raw in CALLBACK.findall(text):
            value = re.sub(r"\{[^}]*\}", "1", raw) if is_f else raw
            if re.fullmatch(r"1+", value):  # préfixe entièrement dynamique (ex. f"{PREFIX}{id}") : non vérifiable
                continue
            found.setdefault(value, origin)
        for name in CONSTANT_USE.findall(text):
            if name in constants:
                found.setdefault(constants[name], origin)
    return found


@pytest.fixture
async def patterns(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("ENABLE_COMMUNITY", "true")
    get_settings.cache_clear()
    load_translations()
    app = await create_bot_application()
    return _collect_patterns([h for hs in app.handlers.values() for h in hs])


# Callbacks gérés hors de CallbackQueryHandler (ex. étapes d'une conversation sur message texte) : à justifier ici.
ALLOWED_WITHOUT_HANDLER: set[str] = set()


async def test_every_callback_button_has_a_handler(patterns):
    orphans = {
        value: origin
        for value, origin in _literal_callbacks().items()
        if value not in ALLOWED_WITHOUT_HANDLER and not any(re.search(p, value) for p in patterns)
    }
    assert orphans == {}, f"boutons sans handler : {orphans}"
