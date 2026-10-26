"""
Orbi — Authentification Web (Phase 10 Admin Dashboard).
Système de connexion par "Magic Link" (Token à usage unique généré via Telegram).
"""

import re
import uuid
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.core.config import get_settings
from src.core.redis import get_redis
from src.models.user import User
from src.web.telegram_auth import InvalidInitDataError, validate_init_data

router = APIRouter()
templates = Jinja2Templates(directory="src/templates")

MAGIC_LINK_PREFIX = "magic_link:"
COOKIE_NAME = "admsession"


class TelegramLoginPayload(BaseModel):
    init_data: str = Field(alias="initData", max_length=8192)
    next: str | None = Field(default=None, max_length=200)


# Redirections après connexion : uniquement des chemins internes connus (jamais d'URL externe).
_SAFE_NEXT = re.compile(r"^/(dev|admin)(/[A-Za-z0-9_\-./?=&%]*)?$")
DEFAULT_AFTER_LOGIN = "/dev/"


def safe_next(value: str | None) -> str:
    if value and _SAFE_NEXT.fullmatch(value) and "//" not in value and ".." not in value:
        return value
    return DEFAULT_AFTER_LOGIN


def set_session_cookie(response, session_id: str, *, embedded: bool = False) -> None:
    """
    Pose le cookie de session. `embedded` : ouverture depuis une Mini App, que Telegram Web charge dans une iframe
    d'un autre site : le cookie doit alors être SameSite=None; Secure; Partitioned pour être renvoyé. Les écritures
    restent protégées par le jeton CSRF, lié à la session.
    """
    settings = get_settings()
    cross_site = embedded and settings.public_https
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        max_age=86400,
        httponly=True,
        secure=True if cross_site else settings.cookie_secure,
        samesite="none" if cross_site else "lax",
        partitioned=cross_site,
    )


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
        location = "/admin/login"
        path = request.url.path
        if request.method == "GET" and path.startswith("/dev"):
            location += f"?next={quote(path, safe='/')}"
        raise HTTPException(status_code=303, headers={"Location": location})
    return admin


@router.get("/login", include_in_schema=False)
async def login_page(request: Request):
    """Affiche la page de connexion (instructions pour le Magic Link)."""
    # Si déjà connecté, redirige
    admin = await get_current_admin(request)
    if admin:
        return RedirectResponse(url="/admin/", status_code=303)

    return templates.TemplateResponse(request, "login.html", {"next": safe_next(request.query_params.get("next"))})


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
    set_session_cookie(response, session_id)
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



@router.post("/telegram-login", include_in_schema=False)
async def telegram_login(payload: TelegramLoginPayload):
    """
    Ouvre une session web à partir de l'`initData` d'une Mini App Telegram (signature vérifiée côté serveur).
    Le compte doit déjà exister (ouvert via le bot) et avoir un rôle administrateur, comme pour le lien magique.
    """
    settings = get_settings()
    try:
        tg_user = validate_init_data(
            payload.init_data, settings.TELEGRAM_BOT_TOKEN, max_age=settings.TELEGRAM_INITDATA_MAX_AGE
        )
    except InvalidInitDataError as e:
        status = 503 if "non configurée" in str(e) else 401
        return JSONResponse({"detail": str(e)}, status_code=status)

    user = await User.find_one(User.telegram_id == tg_user.id)
    if user is None:
        return JSONResponse({"detail": "Compte inconnu : ouvrez d'abord le bot Orbi et envoyez /start."}, status_code=403)
    if user.is_banned or user.role not in ["admin", "superadmin"]:
        return JSONResponse({"detail": "Accès réservé aux administrateurs."}, status_code=403)

    response = JSONResponse({"ok": True, "redirect": safe_next(payload.next)})
    set_session_cookie(response, await create_web_session(user), embedded=True)
    return response
