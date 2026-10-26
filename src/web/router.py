"""
Orbi — Pages d'administration (réglages, utilisateurs, support, système), dans la même enveloppe qu'Orbi Dev.
"""

import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from src.core.config import get_settings
from src.core.database import get_database
from src.core.redis import get_redis
from src.models.ticket import Ticket
from src.models.user import User
from src.orbi_dev.models import Execution
from src.orbi_dev.state import ACTIVE_STATUSES
from src.web.auth import require_admin
from src.web.ui import htmx_target, render

router = APIRouter(prefix="/admin", tags=["Administration"], include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
async def settings_page(request: Request, admin: User = Depends(require_admin)):
    """Réglages : point d'entrée des pages secondaires (connexions, utilisateurs, système)."""
    return render(request, "admin/settings.html", admin, section="settings")


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, admin: User = Depends(require_admin), q: str = ""):
    """Utilisateurs, avec recherche (la saisie est traitée littéralement, jamais comme une expression régulière)."""
    query = {}
    q = q.strip()
    if q:
        try:
            query = {"telegram_id": int(q)}
        except ValueError:
            pattern = re.escape(q[:64])
            query = {"$or": [
                {"username": {"$regex": pattern, "$options": "i"}},
                {"first_name": {"$regex": pattern, "$options": "i"}},
            ]}
    users = await User.find(query).sort("-created_at").limit(50).to_list()
    # Saisie dans le champ de recherche : htmx ne remplace que la liste.
    if htmx_target(request) == "user-rows":
        return render(request, "admin/_user_rows.html", admin, users=users)
    return render(request, "admin/users.html", admin, section="users", users=users, query=q)


@router.get("/tickets", response_class=HTMLResponse)
async def tickets_page(request: Request, admin: User = Depends(require_admin), id: str | None = None):
    """Liste des tickets, ou le détail d'un ticket (?id=)."""
    selected = None
    if id:
        from beanie import PydanticObjectId

        try:
            selected = await Ticket.get(PydanticObjectId(id))
        except Exception:
            selected = None
    tickets = [] if selected else await Ticket.find().sort("-created_at").limit(30).to_list()
    return render(request, "admin/tickets.html", admin, section="tickets", tickets=tickets, selected=selected)


async def _service_up(check) -> bool:
    try:
        await check()
        return True
    except Exception:
        return False


@router.get("/system", response_class=HTMLResponse)
async def system_page(request: Request, admin: User = Depends(require_admin)):
    """État des services et indicateurs d'activité, tous issus de la base."""
    health = [
        ("Base de données", await _service_up(lambda: get_database().command("ping"))),
        ("Cache", await _service_up(lambda: get_redis().ping())),
    ]
    kpis = {
        "users": await User.find(User.is_banned == False).count(),  # noqa: E712
        "open_tickets": await Ticket.find({"status": {"$in": ["open", "in_progress"]}}).count(),
        "active_executions": await Execution.find({"status": {"$in": [s.value for s in ACTIVE_STATUSES]}}).count(),
        "pull_requests": await Execution.find({"pr_url": {"$ne": None}}).count(),
    }
    return render(request, "admin/system.html", admin, section="system", health=health, kpis=kpis,
                  refresh_interval=get_settings().ORBI_DEV_REFRESH_INTERVAL)
