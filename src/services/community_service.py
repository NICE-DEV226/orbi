"""
Orbi — Service Communauté (Phase 6).
Sondages, Karma, Modération.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.models.community import (
    KarmaLog,
    ModerationAction,
    ModerationLog,
    Poll,
)
from src.models.user import User

logger = logging.getLogger("orbi.services.community")


# ─────────────────────────────────────
# Sondages (Polls)
# ─────────────────────────────────────

async def create_poll(
    question: str,
    options: list[str],
    creator_id: int,
    group_id: Optional[int] = None,
    allow_multiple_answers: bool = False,
    end_date: Optional[datetime] = None,
) -> Poll:
    """Crée un nouveau sondage."""
    poll = Poll(
        question=question,
        options=[{"text": opt, "votes": 0} for opt in options],
        creator_telegram_id=creator_id,
        group_id=group_id,
        allow_multiple_answers=allow_multiple_answers,
        end_date=end_date,
    )
    await poll.insert()
    logger.info("Sondage créé: %s (creator=%d)", poll.id, creator_id)
    return poll


async def get_poll(poll_id: str) -> Optional[Poll]:
    """Récupère un sondage par son ID."""
    from beanie import PydanticObjectId
    try:
        return await Poll.get(PydanticObjectId(poll_id))
    except Exception:
        return None


async def get_active_polls(group_id: Optional[int] = None, limit: int = 10) -> list[Poll]:
    """Récupère les sondages actifs."""
    now = datetime.now(timezone.utc)
    query = Poll.find(
        Poll.is_active == True,  # noqa: E712
        {"$or": [{"end_date": None}, {"end_date": {"$gt": now}}]}
    )
    if group_id:
        query = query.find(Poll.group_id == group_id)
    return await query.sort(-Poll.created_at).limit(limit).to_list()


async def vote_poll(poll: Poll, user_id: int, option_indices: list[int]) -> tuple[bool, str]:
    """
    Enregistre un vote pour un sondage.
    Retourne (success, message_error).
    """
    if not poll.is_active:
        return False, "Sondage clôturé."

    if poll.end_date and poll.end_date < datetime.now(timezone.utc):
        poll.is_active = False
        await poll.save()
        return False, "Le sondage a expiré."

    if user_id in poll.voters:
        return False, "Vous avez déjà voté."

    if not poll.allow_multiple_answers and len(option_indices) > 1:
        return False, "Choix multiple non autorisé."

    for idx in option_indices:
        if 0 <= idx < len(poll.options):
            poll.options[idx]["votes"] += 1
            poll.total_votes += 1

    poll.voters.append(user_id)
    await poll.save()
    return True, ""


async def close_poll(poll: Poll) -> None:
    """Clôture un sondage manuellement."""
    poll.is_active = False
    poll.updated_at = datetime.now(timezone.utc)
    await poll.save()


# ─────────────────────────────────────
# Karma
# ─────────────────────────────────────

async def add_karma(
    target_user: User,
    amount: int,
    source_user_id: Optional[int] = None,
    group_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> None:
    """Ajoute (ou retire) des points de Karma à un utilisateur."""
    target_user.karma += amount
    target_user.touch()
    await target_user.save()

    log = KarmaLog(
        user_telegram_id=target_user.telegram_id,
        amount=amount,
        source_telegram_id=source_user_id,
        group_id=group_id,
        reason=reason,
    )
    await log.insert()

    logger.info("Karma %s pour l'utilisateur %d: %s", amount, target_user.telegram_id, reason)


async def get_top_karma_users(limit: int = 10) -> list[User]:
    """Récupère le classement des utilisateurs par Karma."""
    return await User.find().sort(-User.karma).limit(limit).to_list()


# ─────────────────────────────────────
# Modération
# ─────────────────────────────────────

async def log_moderation_action(
    target_telegram_id: int,
    action: ModerationAction,
    moderator_telegram_id: int,
    group_id: Optional[int] = None,
    reason: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> ModerationLog:
    """Enregistre une action de modération (mute, ban, warn)."""
    log = ModerationLog(
        target_telegram_id=target_telegram_id,
        moderator_telegram_id=moderator_telegram_id,
        group_id=group_id,
        action=action,
        reason=reason,
        expires_at=expires_at,
    )
    await log.insert()

    logger.warning(
        "Modération: %s sur l'utilisateur %d par %d (raison: %s)",
        action, target_telegram_id, moderator_telegram_id, reason,
    )
    return log


async def is_user_banned(telegram_id: int, group_id: Optional[int] = None) -> bool:
    """
    Vérifie si un utilisateur a un ban actif.
    (Utilisé potentiellement par middlewares de groupe, non requis pour Phase 1 mais préparé).
    """
    now = datetime.now(timezone.utc)
    query = ModerationLog.find(
        ModerationLog.target_telegram_id == telegram_id,
        ModerationLog.action == ModerationAction.BAN,
        ModerationLog.is_active == True,  # noqa: E712
        {"$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}]}
    )
    if group_id:
        query = query.find(ModerationLog.group_id == group_id)

    count = await query.count()
    return count > 0
