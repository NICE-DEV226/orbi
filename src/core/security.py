"""
Orbi — Vérification des tokens Bearer pour les API admin et développeur.
Fail-closed : un token non configuré côté serveur refuse toutes les requêtes.
"""

import hmac

from fastapi import HTTPException, status


def check_bearer(authorization: str | None, expected: str) -> None:
    """Lève 401/503 sauf si l'en-tête Authorization correspond au token attendu."""
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentification API non configurée")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

