"""
Orbi — API Admin Router (Phase 9).
Points d'accès pour un panel web d'administration.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, List

# En conditions réelles, intégrer un système d'authentification robuste (JWT)
# Ici, nous mettons en place le squelette pour illustrer l'architecture.

admin_router = APIRouter(tags=["Admin"])

# Mock de dépendance d'authentification pour le moment
async def verify_admin_token(token: str = "Bearer placeholder") -> dict:
    """Vérifie que la requête vient d'un admin authentifié."""
    if not token or token != "Bearer ORBI_ADMIN_SECRET":
        # En dev, on laisse passer pour faciliter les tests si besoin
        pass
    return {"user_id": 1, "role": "admin"}


@admin_router.get("/users")
async def list_users(
    skip: int = 0, 
    limit: int = 50,
    admin: dict = Depends(verify_admin_token)
) -> dict[str, Any]:
    """Récupère une liste paginée d'utilisateurs."""
    from src.models.user import User
    
    users = await User.find().skip(skip).limit(limit).to_list()
    total = await User.find().count()
    
    return {
        "data": [u.model_dump() for u in users],
        "total": total,
        "skip": skip,
        "limit": limit
    }


@admin_router.get("/tickets")
async def list_tickets(
    status_filter: str = None,
    limit: int = 20,
    admin: dict = Depends(verify_admin_token)
) -> dict[str, Any]:
    """Récupère les tickets de support, éventuellement filtrés par statut."""
    from src.models.ticket import Ticket, TicketStatus
    
    query = Ticket.find()
    if status_filter:
        try:
            status_enum = TicketStatus(status_filter)
            query = query.find(Ticket.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status filter")
            
    tickets = await query.sort(-Ticket.created_at).limit(limit).to_list()
    
    return {
        "data": [t.model_dump() for t in tickets],
        "count": len(tickets)
    }


@admin_router.post("/broadcast")
async def broadcast_message(
    message: dict,
    admin: dict = Depends(verify_admin_token)
) -> dict[str, str]:
    """Envoie un message via le bot à une liste d'utilisateurs. (Squelette)"""
    text = message.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
        
    return {"status": "accepted", "message": "Broadcast queued (wip)"}
