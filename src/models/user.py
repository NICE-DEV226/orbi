"""
Orbi — Modèle User (Beanie Document).
Représente un utilisateur Telegram dans la base MongoDB.
"""

from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document, Indexed
from pydantic import Field


class UserRole(StrEnum):
    """Rôles utilisateur Orbi."""
    USER = "user"
    AGENT = "agent"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class NotificationPreferences(StrEnum):
    """Types de notifications configurables."""
    ORDER_CONFIRMATIONS = "order_confirmations"
    TICKET_REPLIES = "ticket_replies"
    COMMUNITY_ANNOUNCEMENTS = "community_announcements"
    MORNING_BRIEF = "morning_brief"
    TASK_REMINDERS = "task_reminders"


class User(Document):
    """Document MongoDB représentant un utilisateur Orbi."""

    # ── Identité Telegram ──
    telegram_id: Indexed(int, unique=True)  # type: ignore[valid-type]
    username: str | None = None
    first_name: str = ""
    last_name: str | None = None

    # ── Préférences ──
    language: str | None = Field(default=None, pattern=r"^(fr|en|ar)$")  # None = pas encore choisie (onboarding)
    timezone: str = "UTC"
    role: UserRole = UserRole.USER

    # ── État ──
    is_banned: bool = False
    ban_reason: str | None = None
    banned_at: datetime | None = None
    banned_by: int | None = None  # telegram_id de l'admin qui a banni

    # ── Notifications ──
    enabled_notifications: list[str] = Field(
        default_factory=lambda: [
            NotificationPreferences.ORDER_CONFIRMATIONS,
            NotificationPreferences.TICKET_REPLIES,
            NotificationPreferences.COMMUNITY_ANNOUNCEMENTS,
            NotificationPreferences.MORNING_BRIEF,
            NotificationPreferences.TASK_REMINDERS,
        ]
    )
    morning_brief_hour: int = Field(default=9, ge=0, le=23)

    # ── Statistiques ──
    total_orders: int = 0
    total_tickets: int = 0
    karma_points: int = 0

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "users"
        use_state_management = True

    @property
    def display_name(self) -> str:
        """Nom affiché de l'utilisateur."""
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.username or str(self.telegram_id)

    @property
    def is_admin(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.SUPERADMIN)

    @property
    def is_superadmin(self) -> bool:
        return self.role == UserRole.SUPERADMIN

    def touch(self) -> None:
        """Met à jour les timestamps d'activité."""
        now = datetime.now(UTC)
        self.updated_at = now
        self.last_active_at = now
