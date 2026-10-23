"""
Orbi — Service Développeur (Phase 8).
Logs système, webhooks GitHub, statistiques d'infrastructure.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.config import get_settings
from src.core.redis import get_redis
from src.models.developer import ApiLog, ErrorLog, GithubWebhookLog

logger = logging.getLogger("orbi.services.developer")

# ─────────────────────────────────────
# Webhooks GitHub
# ─────────────────────────────────────

def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """Vérifie la signature webhooks GitHub."""
    settings = get_settings()
    if not settings.GITHUB_WEBHOOK_SECRET:
        logger.error("GITHUB_WEBHOOK_SECRET non défini : webhook GitHub refusé.")
        return False

    if not signature_header:
        return False

    hash_object = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    )
    expected_signature = "sha256=" + hash_object.hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)


async def process_github_webhook(
    event_type: str,
    payload: dict[str, Any],
    delivery_id: str,
) -> GithubWebhookLog:
    """Traite et enregistre un webhook GitHub."""
    action = payload.get("action", "")
    repository = payload.get("repository", {}).get("full_name", "unknown")
    sender = payload.get("sender", {}).get("login", "unknown")
    
    # Extraction ciblée de détails selon le type d'événement
    details = {}
    if event_type == "push":
        commits = payload.get("commits", [])
        if commits:
            details["message"] = commits[-1].get("message", "")
            details["author"] = commits[-1].get("author", {}).get("name", "")
            details["url"] = commits[-1].get("url", "")
    elif event_type in ("issues", "pull_request"):
        item = payload.get(event_type[:-1] if event_type == "issues" else "pull_request", {})
        details["title"] = item.get("title", "")
        details["url"] = item.get("html_url", "")
        details["state"] = item.get("state", "")

    log = GithubWebhookLog(
        event_type=event_type,
        action=action,
        repository=repository,
        sender=sender,
        payload_details=details,
        delivery_id=delivery_id,
    )
    await log.insert()
    logger.info("GitHub Webhook enregistré: %s/%s par %s", event_type, action, sender)
    return log


async def get_recent_github_events(limit: int = 5) -> list[GithubWebhookLog]:
    """Récupère les derniers événements GitHub."""
    return await GithubWebhookLog.find().sort(-GithubWebhookLog.received_at).limit(limit).to_list()


# ─────────────────────────────────────
# Logs d'Erreurs
# ─────────────────────────────────────

async def log_error(
    service: str,
    error_message: str,
    traceback_str: Optional[str] = None,
    user_id: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> ErrorLog:
    """Enregistre une erreur système."""
    err = ErrorLog(
        service=service,
        error_message=error_message,
        traceback=traceback_str,
        user_id=user_id,
        metadata=metadata or {},
    )
    await err.insert()
    logger.error("ErrorLog créé [%s]: %s", service, error_message)
    return err


async def get_unresolved_errors(limit: int = 10) -> list[ErrorLog]:
    """Récupère les erreurs non résolues."""
    return await ErrorLog.find(ErrorLog.is_resolved == False).sort(-ErrorLog.occurred_at).limit(limit).to_list()  # noqa: E712


async def resolve_error(error_id: str, resolved_by: int) -> Optional[ErrorLog]:
    """Marque une erreur comme résolue."""
    from beanie import PydanticObjectId
    try:
        err = await ErrorLog.get(PydanticObjectId(error_id))
        if err:
            err.is_resolved = True
            err.resolved_at = datetime.now(timezone.utc)
            err.resolved_by_telegram_id = resolved_by
            await err.save()
            return err
    except Exception:
        pass
    return None


# ─────────────────────────────────────
# API Logs & Rate Limiting Stats (Phase 8 + Middlewares)
# ─────────────────────────────────────

async def log_api_call(
    endpoint: str,
    method: str,
    status_code: int,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Enregistre un appel API (peut être appelé par un Middleware).
    NB: Si le volume est énorme, utiliser Redis ou un flux asynchrone type Kafka.
    Ici on le met dans MongoDB pour le Dashboard Développeur.
    """
    # Éviter de logger les appels de healthcheck pour ne pas polluer 
    if "health" in endpoint:
        return
        
    api_log = ApiLog(
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        user_id=user_id,
        ip_address=ip_address,
    )
    await api_log.insert()


async def get_api_logs_stats() -> dict[str, Any]:
    """Renvoie quelques statistiques simples sur les appels API."""
    total = await ApiLog.find().count()
    errors_500 = await ApiLog.find(ApiLog.status_code >= 500).count()
    errors_400 = await ApiLog.find(ApiLog.status_code >= 400, ApiLog.status_code < 500).count()
    
    return {
        "total_calls": total,
        "server_errors": errors_500,
        "client_errors": errors_400,
        "success_rate": round(((total - errors_500 - errors_400) / total * 100), 2) if total > 0 else 100.0
    }


async def get_redis_stats() -> dict[str, Any]:
    """Récupère les infos/stats de base de Redis."""
    try:
        redis = get_redis()
        info = await redis.info()
        return {
            "version": info.get("redis_version", "unknown"),
            "uptime_days": info.get("uptime_in_days", 0),
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
        }
    except Exception as e:
        logger.error("Impossible de récupérer les stats Redis: %s", e)
        return {"error": str(e)}
