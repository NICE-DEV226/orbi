"""Orbi Dev — Retrait des secrets courants avant tout stockage ou affichage de texte externe."""

import re

_SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[=:]\s*\S+"),
    re.compile(r"\b(?:sk|ghp|gho|ghs|github_pat|cog|key|crsr)_[A-Za-z0-9_-]{8,}"),
]


def sanitize_text(text: str | None, limit: int = 500) -> str:
    cleaned = text or ""
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned[:limit]
