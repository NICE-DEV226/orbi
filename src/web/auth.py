"""
Orbi — Authentification Web (Phase 10 Admin Dashboard).
Système de connexion par "Magic Link" (Token à usage unique généré via Telegram).
"""

import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.core.config import get_settings
from src.core.redis import get_redis
from src.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="src/templates")

MAGIC_LINK_PREFIX = "magic_link:"
COOKIE_NAME = "admsession"


async def create_web_session(user: User) -> str:
    """Crée une session sécurisée dans Redis pour l'admin."""
    redis = get_redis()
    session_id = str(uuid.uuid4())
    # Session valide pour 24h
    await redis.setex(f"websession:{session_id}", 86400, str(user.telegram_id))
    return session_id


async def get_current_admin(request: Request) -> User | None:
    """Dépendance : récupère l'admin courant depuis le cookie de session."""
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        return None

    redis = get_redis()
    telegram_id = await redis.get(f"websession:{session_id}")

    if not telegram_id:
        return None

    user = await User.find_one(User.telegram_id == int(telegram_id))
    if user and user.role in ["admin", "superadmin"]:
        # Renouvellement silencieux de la session
        await redis.expire(f"websession:{session_id}", 86400)
        return user
    return None


async def require_admin(request: Request) -> User:
    """Protège les routes en redirigeant vers /admin/login si non admin."""
    admin = await get_current_admin(request)
    if not admin:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return admin


@router.get("/login", include_in_schema=False)
async def login_page(request: Request):
    """Affiche la page de connexion (instructions pour le Magic Link)."""
    # Si déjà connecté, redirige
    admin = await get_current_admin(request)
    if admin:
        return RedirectResponse(url="/admin/", status_code=303)

    return templates.TemplateResponse(request, "login.html", {})


@router.get("/auth/{token}", include_in_schema=False)
async def auth_magic_link(token: str, request: Request):
    """Valide le Magic Link et pose le cookie de session."""
    redis = get_redis()
    telegram_id = await redis.get(f"{MAGIC_LINK_PREFIX}{token}")

    if not telegram_id:
        return templates.TemplateResponse(request, "login.html",
            {"error": "Lien invalide ou expiré (durée de validité : 10 minutes)."},
        )

    # Le token est à usage unique : on le supprime
    await redis.delete(f"{MAGIC_LINK_PREFIX}{token}")

    user = await User.find_one(User.telegram_id == int(telegram_id))
    if not user or user.role not in ["admin", "superadmin"]:
        return templates.TemplateResponse(request, "login.html",
            {"error": "Accès refusé. Rôle administrateur requis."},
        )

    # Création de la session
    session_id = await create_web_session(user)

    response = RedirectResponse(url="/admin/", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        max_age=86400,
        httponly=True,  # Protège contre XSS
        secure=get_settings().cookie_secure,
        samesite="lax",
    )
    return response


@router.post("/logout", include_in_schema=False)
async def logout(request: Request):
    """Déconnecte l'administrateur et supprime sa session Redis."""
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        redis = get_redis()
        await redis.delete(f"websession:{session_id}")

    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


# ── Endpoints du Dashboard (Protégés) ──

