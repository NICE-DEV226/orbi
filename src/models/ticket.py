"""
Orbi — Modèle Ticket (Beanie Document).
Système de support avec SLA, priorités, et CSAT.
"""

from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document, Indexed
from pydantic import BaseModel, Field


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(StrEnum):
    URGENT = "urgent"      # SLA: 1h
    HIGH = "high"          # SLA: 4h
    MEDIUM = "medium"      # SLA: 24h
    LOW = "low"            # SLA: 72h


class TicketCategory(StrEnum):
    BILLING = "billing"
    TECHNICAL = "technical"
    GENERAL = "general"
    COMPLAINT = "complaint"
    OTHER = "other"


# SLA en secondes par priorité
SLA_SECONDS = {
    TicketPriority.URGENT: 3600,       # 1h
    TicketPriority.HIGH: 14400,        # 4h
    TicketPriority.MEDIUM: 86400,      # 24h
    TicketPriority.LOW: 259200,        # 72h
}

# Mots-clés pour la détection de priorité urgente
URGENT_KEYWORDS = {
    "fr": ["paiement bloqué", "fraude", "accès impossible", "urgent", "hacké", "volé"],
    "en": ["payment blocked", "fraud", "access denied", "urgent", "hacked", "stolen"],
    "ar": ["الدفع معلق", "احتيال", "وصول مستحيل", "عاجل"],
}


class TicketMessage(BaseModel):
    """Message dans l'historique d'un ticket."""
    role: str  # "user" | "agent"
    text: str
    timestamp: datetime
    attachments: list[str] = Field(default_factory=list)


class Ticket(Document):
    """Document MongoDB représentant un ticket de support."""

    # ── Identifiant unique ──
    ticket_id: Indexed(str, unique=True)  # type: ignore[valid-type]  # Format: TKT-YYYY-NNNNN

    # ── Utilisateur ──
    user_telegram_id: Indexed(int)  # type: ignore[valid-type]
    user_name: str = ""

    # ── Contenu ──
    category: TicketCategory
    subject: str
    description: str

    # ── État ──
    status: TicketStatus = TicketStatus.OPEN
    priority: TicketPriority = TicketPriority.MEDIUM
    assigned_to: int | None = None  # telegram_id de l'agent

    # ── SLA ──
    sla_deadline: datetime | None = None
    sla_breached: bool = False

    # ── Historique des messages ──
    messages: list[dict] = Field(default_factory=list)
    # Chaque message : {"role": "user"|"agent", "text": str, "timestamp": datetime, "attachments": []}

    # ── CSAT ──
    csat_rating: int | None = None  # 1-5
    csat_sent_at: datetime | None = None
    csat_reminder_sent: bool = False

    # ── Escalade ──
    is_escalated: bool = False
    escalation_context: str | None = None

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    closed_at: datetime | None = None

    class Settings:
        name = "tickets"
        use_state_management = True

    @classmethod
    def detect_priority(cls, category: TicketCategory, description: str, lang: str = "fr") -> TicketPriority:
        """Détecte automatiquement la priorité selon la catégorie et les mots-clés."""
        # Réclamation → automatiquement Haute
        if category == TicketCategory.COMPLAINT:
            return TicketPriority.HIGH

        # Vérification des mots-clés urgents
        desc_lower = description.lower()
        keywords = URGENT_KEYWORDS.get(lang, URGENT_KEYWORDS["fr"])
        for keyword in keywords:
            if keyword in desc_lower:
                return TicketPriority.URGENT

        return TicketPriority.MEDIUM
