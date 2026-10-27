"""
Orbi — Authentification Web (Phase 10 Admin Dashboard).
Système de connexion par "Magic Link" (Token à usage unique généré via Telegram).
"""

import re
import sys
import uuid
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from src.core.config import get_settings
from src.core.redis import get_redis
from src.models.user import User
from src.web.telegram_auth import InvalidInitDataError, validate_init_data
from src.web.ui import ASSET_VERSION, templates

router = APIRouter()

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


# L'attribut Partitioned n'est géré nativement par http.cookies (donc par Starlette) qu'à partir de Python 3.14.
_NATIVE_PARTITIONED = sys.version_info >= (3, 14)


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
        partitioned=cross_site and _NATIVE_PARTITIONED,
    )
    if cross_site and not _NATIVE_PARTITIONED:
        # Python < 3.14 : on ajoute l'attribut à la main sur l'en-tête que Starlette vient de produire.
        prefix = f"{COOKIE_NAME}=".encode()
        response.raw_headers = [
            (name, value + b"; Partitioned") if name == b"set-cookie" and value.startswith(prefix) else (name, value)
            for name, value in response.raw_headers
        ]


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
        return RedirectResponse(url=DEFAULT_AFTER_LOGIN, status_code=303)

    return templates.TemplateResponse(
        request, "login.html", {"next": safe_next(request.query_params.get("next")), "asset_v": ASSET_VERSION}
    )


INVALID_LINK = "Ce lien est invalide ou expiré (il est valable 10 minutes et ne sert qu'une fois)."


def _login_page(request: Request, status_code: int = 200, **context):
    response = templates.TemplateResponse(
        request, "login.html", {"asset_v": ASSET_VERSION, **context}, status_code=status_code
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/auth/{token}", include_in_schema=False)
async def magic_link_page(token: str, request: Request):
    """
    Affiche le bouton de connexion, sans consommer le lien.

    Telegram (et d'autres messageries) ouvrent eux-mêmes les liens d'un message pour en faire un aperçu : si un simple
    GET suffisait à se connecter, ce passage automatique brûlerait le lien avant le clic de l'utilisateur.
    """
    if not await get_redis().get(f"{MAGIC_LINK_PREFIX}{token}"):
        return _login_page(request, error=INVALID_LINK)
    return _login_page(request, confirm_token=token)


@router.post("/auth/{token}", include_in_schema=False)
async def auth_magic_link(token: str, request: Request):
    """Valide le Magic Link (usage unique, retiré de façon atomique) et pose le cookie de session."""
    telegram_id = await get_redis().getdel(f"{MAGIC_LINK_PREFIX}{token}")
    if not telegram_id:
        return _login_page(request, status_code=400, error=INVALID_LINK)

    user = await User.find_one(User.telegram_id == int(telegram_id))
    if not user or user.role not in ["admin", "superadmin"]:
        return _login_page(request, status_code=403, error="Accès réservé aux administrateurs.")

    # 303 : le navigateur rejoue la redirection en GET
    response = RedirectResponse(url=DEFAULT_AFTER_LOGIN, status_code=303)
    set_session_cookie(response, await create_web_session(user))
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
