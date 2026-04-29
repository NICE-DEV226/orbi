"""
Orbi — Modèles Communauté (Beanie Documents).
Sondages, karma et modération.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from beanie import Document, Indexed
from pydantic import Field


# ─────────────────────────────────────
# Sondage
# ─────────────────────────────────────

class Poll(Document):
    """Document MongoDB représentant un sondage interactif."""

    # ── Identité ──
    group_chat_id: Indexed(int)  # type: ignore[valid-type]
    message_id: Optional[int] = None  # ID du message Telegram contenant le sondage
    creator_telegram_id: int

    # ── Contenu ──
    question: str = Field(max_length=255)
    options: list[str] = Field(default_factory=list)  # Max 8 options, chaque option max 100 chars
    votes: dict[str, list[int]] = Field(default_factory=dict)
    # {option_index: [telegram_ids]} — vide = anonyme ne stocke pas les ids

    # ── Configuration ──
    is_anonymous: bool = False
    is_closed: bool = False
    close_at: Optional[datetime] = None  # Fermeture automatique

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None

    class Settings:
        name = "polls"

    @property
    def total_votes(self) -> int:
        return sum(len(voters) for voters in self.votes.values())

    def get_results(self) -> list[dict]:
        """Retourne les résultats formatés avec pourcentages."""
        total = self.total_votes
        results = []
        for i, option in enumerate(self.options):
            count = len(self.votes.get(str(i), []))
            pct = round((count / total * 100), 1) if total > 0 else 0
            results.append({"option": option, "count": count, "percentage": pct})
        return results


# ─────────────────────────────────────
# Karma
# ─────────────────────────────────────

class KarmaLog(Document):
    """Document MongoDB loguant chaque attribution de karma."""

    giver_telegram_id: Indexed(int)  # type: ignore[valid-type]
    receiver_telegram_id: Indexed(int)  # type: ignore[valid-type]
    group_chat_id: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "karma_logs"


# ─────────────────────────────────────
# Modération
# ─────────────────────────────────────

class ModerationAction(StrEnum):
    WARNING = "warning"
    MUTE = "mute"
    UNMUTE = "unmute"
    BAN = "ban"
    UNBAN = "unban"
    AUTO_SPAM = "auto_spam"
    AUTO_FLOOD = "auto_flood"
    AUTO_LINKS = "auto_links"
    AUTO_MENTIONS = "auto_mentions"


class ModerationLog(Document):
    """Document MongoDB loguant les actions de modération."""

    # ── Cible ──
    target_telegram_id: Indexed(int)  # type: ignore[valid-type]
    target_username: Optional[str] = None

    # ── Action ──
    action: ModerationAction
    reason: Optional[str] = None
    duration_seconds: Optional[int] = None  # Pour mute

    # ── Contexte ──
    group_chat_id: Optional[int] = None
    admin_telegram_id: Optional[int] = None  # None si automatique
    is_automatic: bool = False

    # ── Expiration ──
    expires_at: Optional[datetime] = None
    is_expired: bool = False

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "moderation_logs"


# ─────────────────────────────────────
# Configuration groupe
# ─────────────────────────────────────

class GroupConfig(Document):
    """Configuration d'un groupe Telegram où Orbi est actif."""

    chat_id: Indexed(int, unique=True)  # type: ignore[valid-type]
    chat_title: str = ""

    # ── Auto-modération ──
    auto_moderation_enabled: bool = True
    max_identical_messages: int = 3        # en 10 secondes
    max_messages_flood: int = 10           # en 30 secondes
    allow_links: bool = True
    max_mentions_per_message: int = 5

    # ── Bienvenue ──
    welcome_message_template: Optional[str] = None
    # Variables : {name}, {group}, {rules_link}, {member_count}

    # ── Règles ──
    rules_text: Optional[str] = None  # Max 2000 chars

    # ── Karma ──
    karma_button_enabled: bool = False

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "group_configs"
