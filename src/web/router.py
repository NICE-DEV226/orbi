"""
Orbi — Routeur principal du Dashboard Web (Phase 10 Admin Dashboard).
Connecte les requêtes HTTP (Navigateur) aux vues HTML (Jinja2).
"""

import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.models.ticket import Ticket
from src.models.user import User
from src.orbi_dev.models import Execution
from src.orbi_dev.state import ACTIVE_STATUSES
from src.web.auth import require_admin

router = APIRouter(prefix="/admin", tags=["Dashboard Web"])
templates = Jinja2Templates(directory="src/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, admin: User = Depends(require_admin)):
    """Affiche la page d'accueil du dashboard avec les KPIs."""

    # Calcul des KPIs (tous issus de la base)
    users = await User.find(User.is_banned == False).count()  # noqa: E712
    open_tickets = await Ticket.find({"status": {"$in": ["open", "in_progress"]}}).count()
    active_executions = await Execution.find(
        {"status": {"$in": [s.value for s in ACTIVE_STATUSES]}}
    ).count()
    pull_requests = await Execution.find({"pr_url": {"$ne": None}}).count()

    recent_tickets = await Ticket.find().sort("-created_at").limit(5).to_list()

    kpis = {
        "users": users,
        "open_tickets": open_tickets,
        "active_executions": active_executions,
        "pull_requests": pull_requests,
    }

    return templates.TemplateResponse(request, "dashboard.html", {
        "admin": admin,
        "active_tab": "home",
        "kpis": kpis,
        "recent_tickets": recent_tickets
    })


@router.get("/users", response_class=HTMLResponse)
async def users_manager(request: Request, admin: User = Depends(require_admin), q: str = ""):
    """Affiche la liste des utilisateurs avec recherche."""
    query = {}
    if q:
        # Recherche par telegram_id (exact), username, ou prénom
        try:
            tid = int(q)
            query = {"telegram_id": tid}
        except ValueError:
            pattern = re.escape(q[:64])
            query = {
                "$or": [
                    {"username": {"$regex": pattern, "$options": "i"}},
                    {"first_name": {"$regex": pattern, "$options": "i"}}
                ]
            }

    users = await User.find(query).sort("-created_at").limit(50).to_list()

    return templates.TemplateResponse(request, "users.html", {
        "admin": admin,
        "active_tab": "users",
        "users": users,
        "query": q
    })


@router.get("/tickets", response_class=HTMLResponse)
async def tickets_manager(request: Request, admin: User = Depends(require_admin), id: str = None):
    """Affiche la file d'attente du support."""
    tickets = await Ticket.find().sort("-created_at").limit(20).to_list()

    selected_ticket = None
    if id:
        from beanie import PydanticObjectId
        try:
            selected_ticket = await Ticket.get(PydanticObjectId(id))
        except Exception:
            pass

    return templates.TemplateResponse(request, "tickets.html", {
        "admin": admin,
        "active_tab": "tickets",
        "tickets": tickets,
        "selected_ticket": selected_ticket,
    })
