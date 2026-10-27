"""
Orbi — Service Tickets (Phase 4).
Logique métier : création, mise à jour, SLA, compteur, CSAT.
"""

import logging
from datetime import UTC, datetime, timedelta

from beanie.operators import In

from src.models.ticket import (
    SLA_SECONDS,
    Ticket,
    TicketCategory,
    TicketStatus,
)
from src.models.user import User

logger = logging.getLogger("orbi.services.ticket")

# Limite de tickets ouverts par utilisateur
MAX_OPEN_TICKETS = 3


async def generate_ticket_id() -> str:
    """Génère un ID de ticket unique : TKT-YYYY-NNNNN."""
    now = datetime.now(UTC)
    year = now.strftime("%Y")

    # Compte les tickets de cette année
    count = await Ticket.find(
        Ticket.ticket_id >= f"TKT-{year}-",
        Ticket.ticket_id <= f"TKT-{year}-99999",
    ).count()

    return f"TKT-{year}-{count + 1:05d}"


async def count_open_tickets(telegram_id: int) -> int:
    """Compte les tickets ouverts d'un utilisateur."""
    return await Ticket.find(
        Ticket.user_telegram_id == telegram_id,
        In(Ticket.status, [TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.WAITING_USER]),
    ).count()


async def create_ticket(
    user: User,
    category: TicketCategory,
    subject: str,
    description: str,
    lang: str = "fr",
) -> Ticket:
    """
    Crée un nouveau ticket de support.
    Détecte automatiquement la priorité et calcule le SLA.
    """
    # Vérification de la limite
    open_count = await count_open_tickets(user.telegram_id)
    if open_count >= MAX_OPEN_TICKETS:
        raise TicketLimitExceededError(open_count)

    # Génération ID et détection priorité
    ticket_id = await generate_ticket_id()
    priority = Ticket.detect_priority(category, description, lang)
    sla_seconds = SLA_SECONDS[priority]
    sla_deadline = datetime.now(UTC) + timedelta(seconds=sla_seconds)

    ticket = Ticket(
        ticket_id=ticket_id,
        user_telegram_id=user.telegram_id,
        user_name=user.display_name,
        category=category,
        subject=subject,
        description=description,
        priority=priority,
        sla_deadline=sla_deadline,
        messages=[{
            "role": "user",
            "text": description,
            "timestamp": datetime.now(UTC).isoformat(),
            "attachments": [],
        }],
    )

    await ticket.insert()

    # Incrémente le compteur de tickets de l'utilisateur
    user.total_tickets += 1
    user.touch()
    await user.save()

    logger.info(
        "Ticket créé: %s (user=%d, cat=%s, prio=%s, sla=%s)",
        ticket_id, user.telegram_id, category, priority, sla_deadline.isoformat(),
    )

    return ticket


async def get_user_tickets(
    telegram_id: int,
    status_filter: list[TicketStatus] | None = None,
    limit: int = 10,
) -> list[Ticket]:
    """Récupère les tickets d'un utilisateur, triés par date de création."""
    query = Ticket.find(Ticket.user_telegram_id == telegram_id)

    if status_filter:
        query = Ticket.find(
            Ticket.user_telegram_id == telegram_id,
            In(Ticket.status, status_filter),
        )

    return await query.sort(-Ticket.created_at).limit(limit).to_list()


async def get_ticket(ticket_id: str) -> Ticket | None:
    """Récupère un ticket par son ID."""
    return await Ticket.find_one(Ticket.ticket_id == ticket_id)


async def add_message(
    ticket: Ticket,
    role: str,
    text: str,
    attachments: list | None = None,
) -> Ticket:
    """Ajoute un message à l'historique du ticket."""
    ticket.messages.append({
        "role": role,
        "text": text,
        "timestamp": datetime.now(UTC).isoformat(),
        "attachments": attachments or [],
    })
    ticket.updated_at = datetime.now(UTC)

    if role == "agent":
        ticket.status = TicketStatus.WAITING_USER
    elif role == "user" and ticket.status == TicketStatus.WAITING_USER:
        ticket.status = TicketStatus.IN_PROGRESS

    await ticket.save()
    return ticket


async def resolve_ticket(ticket: Ticket) -> Ticket:
    """Marque un ticket comme résolu et programme l'envoi du CSAT."""
    ticket.status = TicketStatus.RESOLVED
    ticket.resolved_at = datetime.now(UTC)
    ticket.updated_at = datetime.now(UTC)
    await ticket.save()

    logger.info("Ticket résolu: %s", ticket.ticket_id)
    return ticket


async def close_ticket(ticket: Ticket) -> Ticket:
    """Ferme définitivement un ticket."""
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = datetime.now(UTC)
    ticket.updated_at = datetime.now(UTC)
    await ticket.save()

    logger.info("Ticket fermé: %s", ticket.ticket_id)
    return ticket


async def save_csat_rating(ticket: Ticket, rating: int) -> Ticket:
    """Enregistre la note CSAT (1-5) pour un ticket résolu."""
    ticket.csat_rating = max(1, min(5, rating))
    ticket.updated_at = datetime.now(UTC)
    await ticket.save()

    logger.info("CSAT reçu: ticket=%s, rating=%d", ticket.ticket_id, rating)
    return ticket


async def check_sla_breaches() -> list[Ticket]:
    """Vérifie les tickets dont le SLA est dépassé (pour APScheduler)."""
    now = datetime.now(UTC)
    breached = await Ticket.find(
        In(Ticket.status, [TicketStatus.OPEN, TicketStatus.IN_PROGRESS]),
        Ticket.sla_breached == False,  # noqa: E712
        Ticket.sla_deadline <= now,
    ).to_list()

    for ticket in breached:
        ticket.sla_breached = True
        ticket.updated_at = now
        await ticket.save()
        logger.warning("SLA dépassé: %s (deadline=%s)", ticket.ticket_id, ticket.sla_deadline)

    return breached


async def get_pending_csat_tickets() -> list[Ticket]:
    """Récupère les tickets résolus sans CSAT (pour rappel APScheduler)."""
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    return await Ticket.find(
        Ticket.status == TicketStatus.RESOLVED,
        Ticket.csat_rating == None,  # noqa: E711
        Ticket.csat_sent_at != None,  # noqa: E711
        Ticket.csat_reminder_sent == False,  # noqa: E712
        Ticket.csat_sent_at <= cutoff,
    ).to_list()


# ── Exceptions ──

class TicketLimitExceededError(Exception):
    """L'utilisateur a atteint la limite de tickets ouverts."""
    def __init__(self, count: int):
        self.count = count
        super().__init__(f"Limite de tickets atteinte: {count}/{MAX_OPEN_TICKETS}")
