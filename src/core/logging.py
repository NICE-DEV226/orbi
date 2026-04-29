"""
Orbi — Logging structuré.
JSON en production, formaté lisible en développement.
"""

import logging
import sys
from typing import Any

from src.core.config import get_settings


class JsonFormatter(logging.Formatter):
    """Formateur JSON pour les logs en production."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone

        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Champs extra
        for key in ("user_id", "telegram_id", "request_id", "endpoint"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging() -> None:
    """Configure le logging global d'Orbi."""
    settings = get_settings()
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Handler console
    handler = logging.StreamHandler(sys.stdout)

    if settings.is_production:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s │ %(levelname)-8s │ %(name)-25s │ %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Réduire le bruit des librairies tierces
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)

    logging.getLogger("orbi").info("Logging configuré (level=%s, env=%s)", settings.LOG_LEVEL, settings.ENVIRONMENT)
