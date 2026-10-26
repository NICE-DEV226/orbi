"""
Orbi — Service Productivité (Phase 7).
Gestionnaires de Tâches, Notes Personnelles (avec auto-hashtags).
Mode Focus (Pomodoro) basé sur Redis pour éviter la surcharge DB des timers.
"""

import json
import logging
import re
from datetime import UTC, datetime

from src.core.redis import get_redis
from src.models.productivity import Note, Task, TaskPriority, TaskStatus

logger = logging.getLogger("orbi.services.productivity")

# ─────────────────────────────────────
# Mode Focus (Pomodoro) via Redis
# ─────────────────────────────────────
# Pour éviter de flood MongoDB avec un état qui change souvent (play/pause/stop),
# on utilise Redis avec un TTL correspondant à la durée max d'une session.

FOCUS_PREFIX = "orbi:focus:"
FOCUS_TTL = 36000  # 10 heures max par session

async def start_focus_session(telegram_id: int, duration_minutes: int, focus_type: str = "pomodoro") -> dict:
    """Démarre une session de Focus."""
    redis = get_redis()
    key = f"{FOCUS_PREFIX}{telegram_id}"

    now = datetime.now(UTC)
    session_data = {
        "user_id": telegram_id,
        "type": focus_type,
        "duration_minutes": duration_minutes,
        "start_time": now.isoformat(),
        "status": "running",
    }

    await redis.set(key, json.dumps(session_data), ex=FOCUS_TTL)
    logger.info("Focus session démarrée: user=%d, durée=%d min", telegram_id, duration_minutes)
    return session_data

async def get_active_focus_session(telegram_id: int) -> dict | None:
    """Récupère la session Focus active de l'utilisateur."""
    redis = get_redis()
    key = f"{FOCUS_PREFIX}{telegram_id}"
    raw = await redis.get(key)
    if not raw:
        return None
    return json.loads(raw)

async def stop_focus_session(telegram_id: int) -> None:
    """Arrête (supprime) la session Focus en cours."""
    redis = get_redis()
    key = f"{FOCUS_PREFIX}{telegram_id}"
    await redis.delete(key)
    logger.info("Focus session arrêtée: user=%d", telegram_id)


# ─────────────────────────────────────
# Gestion des Tâches (To-Do)
# ─────────────────────────────────────

async def create_task(
    user_id: int,
    title: str,
    priority: TaskPriority = TaskPriority.MEDIUM,
    due_date: datetime | None = None,
    group_id: int | None = None,
) -> Task:
    """Crée une nouvelle tâche."""
    task = Task(
        user_telegram_id=user_id,
        title=title,
        priority=priority,
        due_date=due_date,
        group_id=group_id,
    )
    await task.insert()
    logger.info("Tâche créée: %s (user=%d)", task.id, user_id)
    return task

async def get_user_tasks(user_id: int, limit: int = 10, include_completed: bool = False) -> list[Task]:
    """Récupère les tâches d'un utilisateur, triées par priorité puis date."""
    query = Task.find(Task.user_telegram_id == user_id)

    if not include_completed:
        query = query.find(Task.status != TaskStatus.COMPLETED)

    return await query.sort("priority", "due_date").limit(limit).to_list()

async def get_task(task_id: str) -> Task | None:
    """Récupère une tâche spécifique."""
    from beanie import PydanticObjectId
    try:
        return await Task.get(PydanticObjectId(task_id))
    except Exception:
        return None

async def toggle_task_completion(task: Task) -> Task:
    """Bascule l'état (terminé/non terminé) d'une tâche."""
    done = task.status != TaskStatus.COMPLETED
    task.status = TaskStatus.COMPLETED if done else TaskStatus.ACTIVE
    task.completed_at = datetime.now(UTC) if done else None
    task.updated_at = datetime.now(UTC)
    await task.save()
    return task

async def delete_task(task: Task) -> None:
    """Supprime une tâche définitivement."""
    await task.delete()

async def get_pending_reminders() -> list[Task]:
    """Récupère les tâches avec échéance imminente (pour APScheduler)."""
    now = datetime.now(UTC)
    # Tâches actives dont l'échéance est passée et dont le rappel du jour n'a pas encore été envoyé
    return await Task.find(
        Task.status == TaskStatus.ACTIVE,
        Task.reminder_day_sent == False,  # noqa: E712
        Task.due_date != None,  # noqa: E711
        Task.due_date <= now,
    ).to_list()


# ─────────────────────────────────────
# Notes Personnelles
# ─────────────────────────────────────

def extract_hashtags(text: str) -> list[str]:
    """Extrait tous les hashtags (#mot) d'un texte."""
    return list(set(re.findall(r"#(\w+)", text)))

async def create_note(
    user_id: int,
    content: str,
    voice_file_id: str | None = None,
) -> Note:
    """Crée une nouvelle note, extrayant automatiquement les hashtags."""
    hashtags = extract_hashtags(content)
    note = Note(
        user_telegram_id=user_id,
        content=content,
        hashtags=hashtags,
        voice_file_id=voice_file_id,
    )
    await note.insert()
    logger.info("Note créée: %s (user=%d, tags=%s)", note.id, user_id, hashtags)
    return note

async def get_user_notes(user_id: int, hashtag: str | None = None, limit: int = 10) -> list[Note]:
    """Récupère les notes d'un utilisateur, éventuellement filtrées par hashtag."""
    query = Note.find(Note.user_telegram_id == user_id)

    if hashtag:
        # Recherche la présence du hashtag dans le tableau
        query = query.find({"hashtags": hashtag.strip("#")})

    return await query.sort(-Note.created_at).limit(limit).to_list()

async def delete_note(note: Note) -> None:
    """Supprime une note."""
    await note.delete()
