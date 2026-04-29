"""
Orbi — Modèles Développeurs (Beanie Documents).
API Keys, Webhooks sortants, et logs.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from beanie import Document, Indexed
from pydantic import Field


# ─────────────────────────────────────
# API Key
# ─────────────────────────────────────

class ApiKeyEnvironment(StrEnum):
    PRODUCTION = "production"
    SANDBOX = "sandbox"


AVAILABLE_SCOPES = [
    "read:users",
    "write:broadcast",
    "manage:webhooks",
    "read:orders",
    "write:orders",
    "read:analytics",
    "sandbox",
]


class ApiKey(Document):
    """Document MongoDB représentant une clé API développeur."""

    # ── Identité ──
    owner_telegram_id: Indexed(int)  # type: ignore[valid-type]
    name: str
    prefix: Indexed(str, unique=True)  # type: ignore[valid-type]  # ex: orbi_sk_prod_xxxx

    # ── Sécurité ── La clé complète n'est JAMAIS stockée
    key_hash: str  # SHA256 hash de la clé complète

    # ── Configuration ──
    environment: ApiKeyEnvironment = ApiKeyEnvironment.PRODUCTION
    scopes: list[str] = Field(default_factory=list)

    # ── Rate limiting ──
    rate_limit_per_minute: int = 60  # 60 en prod, 120 en sandbox

    # ── État ──
    is_active: bool = True
    revoked_at: Optional[datetime] = None

    # ── Statistiques ──
    total_requests: int = 0
    last_used_at: Optional[datetime] = None

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "api_keys"

    @property
    def is_sandbox(self) -> bool:
        return self.environment == ApiKeyEnvironment.SANDBOX

    def has_scope(self, scope: str) -> bool:
        """Vérifie si la clé a le scope requis."""
        return scope in self.scopes


# ─────────────────────────────────────
# Webhook sortant
# ─────────────────────────────────────

WEBHOOK_EVENTS = [
    "order.paid",
    "order.shipped",
    "order.cancelled",
    "order.refunded",
    "ticket.created",
    "ticket.resolved",
    "ticket.closed",
    "user.banned",
    "broadcast.sent",
    "product.out_of_stock",
]


class WebhookConfig(Document):
    """Document MongoDB représentant un webhook sortant configuré."""

    # ── Propriétaire ──
    owner_telegram_id: Indexed(int)  # type: ignore[valid-type]
    name: str

    # ── Configuration ──
    url: str  # HTTPS requis en production
    secret: str  # Pour la signature HMAC SHA256
    events: list[str] = Field(default_factory=list)

    # ── État ──
    is_active: bool = True
    consecutive_failures: int = 0  # 10 → désactivation auto

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_triggered_at: Optional[datetime] = None
    disabled_at: Optional[datetime] = None

    class Settings:
        name = "webhook_configs"

    @property
    def should_auto_disable(self) -> bool:
        """10 échecs consécutifs → désactivation automatique."""
        return self.consecutive_failures >= 10


class WebhookDelivery(Document):
    """Log d'une tentative de livraison de webhook."""

    webhook_id: str  # Référence vers WebhookConfig
    event: str
    payload: dict = Field(default_factory=dict)

    # ── Résultat ──
    http_status: Optional[int] = None
    response_time_ms: Optional[float] = None
    is_success: bool = False
    is_test: bool = False
    error_message: Optional[str] = None

    # ── Retry ──
    attempt_number: int = 1  # 1 à 5
    next_retry_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "webhook_deliveries"


# ─────────────────────────────────────
# Log de requête API
# ─────────────────────────────────────

class ApiRequestLog(Document):
    """Log d'une requête API faite avec une clé développeur."""

    api_key_prefix: str
    method: str  # GET, POST, etc.
    endpoint: str
    status_code: int
    response_time_ms: float
    is_sandbox: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "api_request_logs"


class ApiLog(Document):
    """Log simple d'un appel API."""
    endpoint: str
    method: str
    status_code: int
    user_id: Optional[int] = None
    ip_address: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "api_logs"


class ErrorLog(Document):
    """Log d'erreur applicative."""
    service: str
    error_message: str
    traceback: Optional[str] = None
    user_id: Optional[int] = None
    metadata: dict = Field(default_factory=dict)
    
    is_resolved: bool = False
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    resolved_by_telegram_id: Optional[int] = None

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
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "github_webhook_logs"

