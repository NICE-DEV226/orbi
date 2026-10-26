"""Le bot envoie en HTML : le texte saisi par un utilisateur ou reçu d'un tiers doit être échappé."""

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.core.text import esc
from src.models.user import User

SRC = Path(__file__).resolve().parent.parent / "src"
EVIL = '<a href="https://evil.example">gagnez</a>'


def test_esc_neutralises_html_and_handles_none():
    assert esc(EVIL) == '&lt;a href="https://evil.example"&gt;gagnez&lt;/a&gt;'
    assert esc("a & b") == "a &amp; b"
    assert esc(None) == ""
    assert esc(42) == "42"


class TestLeaderboard:
    async def _render(self) -> str:
        from src.handlers.community import show_leaderboard

        me = await User(telegram_id=1, first_name="Moi", karma_points=1).insert()
        await User(telegram_id=2, first_name=EVIL, karma_points=50).insert()
        await User(telegram_id=3, first_name="Silencieux", karma_points=0).insert()
        query = MagicMock()
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()
        context.user_data = {"db_user": me, "lang": "fr"}

        await show_leaderboard(update, context)

        return query.edit_message_text.call_args.args[0]

    async def test_display_names_cannot_inject_html(self):
        text = await self._render()
        assert "<a href" not in text
        assert "&lt;a href" in text

    async def test_only_members_who_earned_karma_are_listed(self):
        text = await self._render()
        assert "Silencieux" not in text


# Champs saisis par un utilisateur ou reçus d'un tiers : ils doivent être entourés de esc(...) quand ils sont insérés
# dans une f-string (donc dans un message HTML). Les libellés de boutons ne sont pas interprétés en HTML.
RISKY = (
    "display_name", "first_name", "username", "question", "title", "subject", "description", "content",
    "error_message", "user_name", "chat_title", "rules_text", "sender", "event_type", "service",
)
BRACES = re.compile(r"\{([^{}]*)\}")
IGNORE_LINE = re.compile(r"logger\.|callback_data|InlineKeyboardButton\(|query\.answer\(|raise |#")


def _unescaped_uses() -> list[str]:
    problems = []
    paths = list((SRC / "handlers").glob("*.py")) + list((SRC / "services").glob("*.py"))
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if 'f"' not in line and "f'" not in line and "{" not in line:
                continue
            if IGNORE_LINE.search(line):
                continue
            for expr in BRACES.findall(line):
                if expr.lstrip().startswith(("t(", "translate")):  # clés de traduction, pas du texte utilisateur
                    continue
                if any(re.search(rf"\.{attr}\b(?!\()|\[['\"]{attr}['\"]\]", expr) for attr in RISKY) and "esc(" not in expr:
                    problems.append(f"{path.relative_to(SRC.parent)}:{number}: {{{expr}}}")
    return problems


def test_no_untrusted_field_is_interpolated_without_esc():
    assert _unescaped_uses() == []
