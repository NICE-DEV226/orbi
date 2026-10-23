"""
Orbi — Configuration centralisée via pydantic-settings.
Charge toutes les variables d'environnement requises (section 10.2 du CdC).
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, MongoDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration globale d'Orbi, validée au démarrage."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Environnement ──
    ENVIRONMENT: Literal["production", "staging", "development"] = "development"
    BASE_URL: str = "http://localhost:8000"

    # ── Telegram ──
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_URL: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    ADMIN_CHAT_ID: int = 0

    # ── MongoDB ──
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "orbi_dev"

    # ── Redis ──
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT ──
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60 * 24  # 24h

    # ── Tokens API (Bearer) — vides = routes correspondantes refusées ──
    ADMIN_API_TOKEN: str = ""
    DEV_API_TOKEN: str = ""

    # ── GitHub ──
    GITHUB_WEBHOOK_SECRET: str = ""

    # ── Stripe ──
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ── Orange Money ──
    ORANGE_MONEY_API_KEY: str = ""
    ORANGE_MONEY_API_SECRET: str = ""
    ORANGE_MONEY_MERCHANT_ID: str = ""

    # ── Wave ──
    WAVE_API_KEY: str = ""
    WAVE_WEBHOOK_SECRET: str = ""

    # ── OpenAI (Whisper) ──
    OPENAI_API_KEY: str = ""

    # ── APIs externes ──
    EXCHANGE_RATES_API_KEY: str = ""
    LIBRETRANSLATE_URL: str = "http://libretranslate:5000"

    # ── Logging ──
    LOG_LEVEL: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def use_webhook(self) -> bool:
        """En production, on utilise les webhooks Telegram. En dev, le polling."""
        return self.is_production and bool(self.TELEGRAM_WEBHOOK_URL)


@lru_cache
def get_settings() -> Settings:
    """Retourne un singleton des settings (cache LRU)."""
    return Settings()
