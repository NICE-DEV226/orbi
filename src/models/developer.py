"""
Orbi — Modèles Développeurs (Beanie Documents).
Logs d'appels API, journal d'erreurs et événements GitHub reçus.
"""

from datetime import UTC, datetime

from beanie import Document
from pydantic import Field


class ApiLog(Document):
    """Log simple d'un appel API."""
    endpoint: str
    method: str
    status_code: int
    user_id: int | None = None
    ip_address: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "api_logs"


class ErrorLog(Document):
    """Log d'erreur applicative."""
    service: str
    error_message: str
    traceback: str | None = None
    user_id: int | None = None
    metadata: dict = Field(default_factory=dict)

    is_resolved: bool = False
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolved_by_telegram_id: int | None = None

    class Settings:
        name = "error_logs"


class GithubWebhookLog(Document):
    """Log d'un événement GitHub reçu."""
    event_type: str
    action: str
    repository: str
    sender: str
    payload_details: dict = Field(default_factory=dict)
    delivery_id: str
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "github_webhook_logs"

