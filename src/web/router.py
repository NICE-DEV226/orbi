"""
Orbi — Routeur principal du Dashboard Web (Phase 10 Admin Dashboard).
Connecte les requêtes HTTP (Navigateur) aux vues HTML (Jinja2).
"""

import re
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.models.user import User
from src.models.ticket import Ticket
from src.models.commerce import Order, Product
from src.web.auth import get_current_admin, require_admin

router = APIRouter(prefix="/admin", tags=["Dashboard Web"])
templates = Jinja2Templates(directory="src/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, admin: User = Depends(require_admin)):
    """Affiche la page d'accueil du dashboard avec les KPIs."""
    
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Calcul des KPIs
    active_users = await User.find(User.is_banned == False).count()
    open_tickets = await Ticket.find({"status": {"$in": ["open", "in_progress"]}}).count()
    orders_today = await Order.find(Order.created_at >= today_start).count()
    
    # Historique de la semaine
    recent_tickets = await Ticket.find().sort("-created_at").limit(5).to_list()
    
    kpis = {
        "active_users": active_users,
        "open_tickets": open_tickets,
        "orders_today": orders_today,
        "revenue_7d": "1250.00" # TODO: Calcul réel sur les Order payées
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
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
    
    return templates.TemplateResponse("users.html", {
        "request": request,
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
            
    # Helper Jinja2 pour accéder à datetime.now
    def now_func():
        return datetime.now(timezone.utc)
            
    return templates.TemplateResponse("tickets.html", {
        "request": request,
        "admin": admin,
        "active_tab": "tickets",
        "tickets": tickets,
        "selected_ticket": selected_ticket,
        "now": now_func
    })


@router.get("/broadcasts", response_class=HTMLResponse)
async def broadcasts_manager(request: Request, admin: User = Depends(require_admin)):
    """Affiche l'interface de diffusion de messages."""
    # Simulation des derniers broadcasts pour l'UI (le modèle Broadcast n'ayant pas été requis jusqu'ici)
    mock_broadcasts = [
         {
             "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
             "message_fr": "Alerte maintenance : le service sera indisponible de 2h à 4h cette nuit.",
             "target_lang": "all",
             "delivered_count": 1450,
             "failed_count": 12
         }
    ]
    
    return templates.TemplateResponse("broadcasts.html", {
        "request": request,
        "admin": admin,
        "active_tab": "broadcasts",
        "broadcasts": mock_broadcasts
    })
