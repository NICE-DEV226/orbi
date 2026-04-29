"""
Orbi — API Dev Router (Phase 9).
Points d'accès pour les développeurs (logs, monitoring, webhooks).
"""

from fastapi import APIRouter, Depends
from typing import Any

from src.services.developer_service import (
    get_api_logs_stats,
    get_redis_stats,
    get_unresolved_errors,
)

dev_router = APIRouter(tags=["Developer"])

# Même logique que pour l'admin, on masque derrière un token dev
async def verify_dev_token(token: str = "Bearer placeholder") -> dict:
    """Vérifie que la requête vient d'un dev authentifié."""
    return {"role": "developer"}


@dev_router.get("/health/stats")
async def infra_stats(dev: dict = Depends(verify_dev_token)) -> dict[str, Any]:
    """Récupère les statistiques détaillées de l'infrastructure."""
    import asyncio
    api_stats, redis_stats = await asyncio.gather(
        get_api_logs_stats(),
        get_redis_stats()
    )
    
    return {
        "api_mongodb": api_stats,
        "redis_cache": redis_stats,
        "status": "ok" if not "error" in redis_stats else "degraded"
    }


@dev_router.get("/errors/unresolved")
async def unresolved_errors(dev: dict = Depends(verify_dev_token)) -> dict[str, Any]:
    """Liste les exceptions critiques non résolues du système."""
    errors = await get_unresolved_errors(limit=20)
    
    return {
        "count": len(errors),
        "errors": [e.model_dump() for e in errors]
    }


@dev_router.post("/test-log")
async def test_error_log(
    service: str, 
    message: str, 
    dev: dict = Depends(verify_dev_token)
) -> dict[str, str]:
    """Force la création d'une erreur dans les logs (utile pour tester le dashboard)."""
    from src.services.developer_service import log_error
    
    err = await log_error(
        service=service,
        error_message=message,
        metadata={"source": "api_test"}
    )
    
    return {"status": "created", "error_id": str(err.id)}
