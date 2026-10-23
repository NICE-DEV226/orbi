"""
Orbi — Point d'entrée FastAPI.
Lifespan : init DB, Redis, i18n au démarrage. Fermeture propre à l'arrêt.
Endpoints : /health, /metrics, /docs, /redoc.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.core.database import close_db, init_db
from src.core.i18n import load_translations
from src.core.logging import setup_logging
from src.core.performance import cleanup_performance_optimizations, init_performance_optimizations
from src.core.redis import close_redis, get_redis, init_redis

logger = logging.getLogger("orbi.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie de l'application : démarrage et arrêt propre."""
    # ── Démarrage ──
    setup_logging()
    logger.info("🚀 Orbi démarre...")

    # Chargement des traductions
    load_translations()
    logger.info("🌍 Traductions chargées")

    # Connexion MongoDB
    await init_db()
    logger.info("🍃 MongoDB connecté")

    # Connexion Redis
    await init_redis()
    logger.info("🔴 Redis connecté")

    # Initialiser les optimisations de performance
    await init_performance_optimizations()
    logger.info("⚡ Optimisations de performance initialisées")

    bot_app = None
    scheduler_started = False
    try:
        # Démarrage du bot Telegram
        from src.bot.app import create_bot_application, start_bot, stop_bot
        bot_app = await create_bot_application()
        await start_bot(bot_app)
        app.state.bot_app = bot_app  # Stocke la référence pour les webhooks
        logger.info("🤖 Bot Telegram démarré")

        # Démarrage APScheduler (SLA alerts, CSAT reminders)
        from src.services.scheduler import start_scheduler, stop_scheduler
        await start_scheduler(bot_app.bot)
        scheduler_started = True
        logger.info("⏰ APScheduler démarré")
    except Exception as e:
        logger.error(f"⚠️ Impossible de démarrer le bot (Le Web UI reste dispo) : {e}")
        app.state.bot_app = None

    logger.info("✅ Orbi prêt — env=%s", get_settings().ENVIRONMENT)

    yield

    # ── Arrêt ──
    logger.info("🛑 Orbi s'arrête...")
    try:
        if scheduler_started:
            from src.services.scheduler import stop_scheduler
            await stop_scheduler()
        if bot_app is not None:
            from src.bot.app import stop_bot
            await stop_bot(bot_app)
    except Exception:
        logger.exception("Erreur à l'arrêt du bot/scheduler")
    finally:
        await cleanup_performance_optimizations()
        await close_redis()
        await close_db()
    logger.info("👋 Orbi arrêté proprement")


def create_app() -> FastAPI:
    """Factory pour créer l'application FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title="Orbi API",
        description="Assistant Universel Telegram — API REST & Webhooks",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc",
    )

    # ── Health check ──
    @app.get("/health", tags=["Infrastructure"])
    async def health_check():
        """Health check : DB, Redis, Bot. HTTP 200 si OK, 503 sinon."""
        from typing import Any
        health: dict[str, Any] = {"status": "ok", "services": {}}

        # Check MongoDB
        try:
            from src.core.database import get_database
            db = get_database()
            await db.command("ping")
            health["services"]["mongodb"] = "ok"
        except Exception as e:
            logger.error("Health check MongoDB en échec: %s", e)
            health["services"]["mongodb"] = "error"
            health["status"] = "degraded"

        # Check Redis
        try:
            redis = get_redis()
            await redis.ping()
            health["services"]["redis"] = "ok"
        except Exception as e:
            logger.error("Health check Redis en échec: %s", e)
            health["services"]["redis"] = "error"
            health["status"] = "degraded"

        status_code = 200 if health["status"] == "ok" else 503
        return JSONResponse(content=health, status_code=status_code)

    # ── Enregistrement des routers API (Phase 9) ──
    from src.api.admin import admin_router
    from src.api.dev import dev_router

    app.include_router(admin_router, prefix="/api/v1/admin")
    app.include_router(dev_router, prefix="/api/v1/dev")

    # ── Enregistrement du Dashboard Web (Phase 10) ──
    from src.web.auth import router as web_auth_router
    from src.web.router import router as web_dashboard_router

    # Montage optionnel de statiques si nécessaires un jour
    # app.mount("/static", StaticFiles(directory="src/static"), name="static")

    app.include_router(web_auth_router, prefix="/admin")
    app.include_router(web_dashboard_router)

    from fastapi import BackgroundTasks, HTTPException, Request

    # ── Webhook Telegram (mode production) ──
    @app.post("/webhook/telegram", include_in_schema=False)
    async def telegram_webhook(request: Request) -> dict:
        import hmac

        from telegram import Update

        expected = get_settings().TELEGRAM_WEBHOOK_SECRET
        bot_app = getattr(request.app.state, "bot_app", None)
        if not expected or bot_app is None:
            raise HTTPException(status_code=503, detail="Webhook Telegram indisponible")

        received = request.headers.get("x-telegram-bot-api-secret-token", "")
        if not hmac.compare_digest(received.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Secret invalide")

        update = Update.de_json(await request.json(), bot_app.bot)
        await bot_app.process_update(update)
        return {"status": "ok"}

    # ── Webhooks GitHub (Phase 8) ──
    @app.post("/webhook/github")
    async def github_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
        from src.services.developer_service import process_github_webhook, verify_github_signature

        sig_header = request.headers.get("x-hub-signature-256", "")
        event_type = request.headers.get("x-github-event", "")
        delivery_id = request.headers.get("x-github-delivery", "")

        payload_bytes = await request.body()

        if not verify_github_signature(payload_bytes, sig_header):
            raise HTTPException(status_code=401, detail="Signature invalide")

        try:
            payload = await request.json()
        except Exception:
            return {"status": "error", "reason": "invalid_json"}

        # Traiter l'événement en arrière-plan
        background_tasks.add_task(process_github_webhook, event_type, payload, delivery_id)

        return {"status": "accepted"}

    return app


# Instance globale
app = create_app()
