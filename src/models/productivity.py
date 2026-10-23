"""
Orbi — Modèles Productivité (Beanie Documents).
Tâches, rappels et notes personnelles.
"""

from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document, Indexed
from pydantic import Field

# ─────────────────────────────────────
# Tâche
# ─────────────────────────────────────

class TaskStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(Document):
    """Document MongoDB représentant une tâche personnelle."""

    user_telegram_id: Indexed(int)  # type: ignore[valid-type]

    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.ACTIVE
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: datetime | None = None

    # ── Rappels ──
    reminder_eve_sent: bool = False   # Rappel veille envoyé
    reminder_day_sent: bool = False   # Rappel jour J envoyé

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    class Settings:
        name = "tasks"

    @property
    def is_overdue(self) -> bool:
        if self.due_date and self.status == TaskStatus.ACTIVE:
            return datetime.now(UTC) > self.due_date
        return False


# ─────────────────────────────────────
# Rappel ponctuel
# ─────────────────────────────────────

class Reminder(Document):
    """Document MongoDB représentant un rappel one-shot."""

    user_telegram_id: Indexed(int)  # type: ignore[valid-type]

    message: str
    remind_at: datetime
    is_sent: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "reminders"


# ─────────────────────────────────────
# Note
# ─────────────────────────────────────

class Note(Document):
    """Document MongoDB représentant une note personnelle."""

    user_telegram_id: Indexed(int)  # type: ignore[valid-type]

    title: str
    content: str = ""
    tags: list[str] = Field(default_factory=list)  # Extraits automatiquement des #hashtags

    # ── Transcription vocale ──
    is_voice_note: bool = False
    voice_file_id: str | None = None
    voice_duration_seconds: int | None = None

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "notes"

    @staticmethod
    def extract_tags(text: str) -> list[str]:
        """Extrait les hashtags d'un texte."""
        import re
        return list(set(re.findall(r"#(\w+)", text)))
