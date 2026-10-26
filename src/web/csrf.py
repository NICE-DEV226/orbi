"""
Orbi — Protection CSRF des formulaires du dashboard.

Jeton dérivé de la session (HMAC-SHA256 de l'identifiant de session avec JWT_SECRET) : il change à chaque
connexion, n'est valable que pour la session qui l'a reçu, et n'exige aucun stockage supplémentaire.
"""

import hashlib
import hmac

from fastapi import HTTPException, Request

from src.core.config import get_settings

COOKIE_NAME = "admsession"


def csrf_token(session_id: str) -> str:
    key = get_settings().JWT_SECRET.encode()
    return hmac.new(key, f"csrf:{session_id}".encode(), hashlib.sha256).hexdigest()


def csrf_token_for(request: Request) -> str:
    return csrf_token(request.cookies.get(COOKIE_NAME, ""))


async def csrf_protect(request: Request) -> None:
    """Dépendance des routes qui modifient l'état : refuse (403) sans jeton valide pour cette session."""
    session_id = request.cookies.get(COOKIE_NAME, "")
    # En-tête (requêtes htmx) ou champ de formulaire (soumission classique) : l'un des deux suffit, il doit être valide.
    submitted = request.headers.get("x-csrf-token") or str((await request.form()).get("csrf_token", ""))
    if not session_id or not hmac.compare_digest(submitted.encode(), csrf_token(session_id).encode()):
        raise HTTPException(status_code=403, detail="Jeton CSRF invalide")
