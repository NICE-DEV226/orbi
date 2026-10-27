"""
Orbi Dev — Vérifier un dépôt sur GitHub avant de l'ajouter.

Une seule requête publique, sans jeton (Orbi n'a aucune clé GitHub) : le dépôt existe-t-il, quelle est sa branche par
défaut. Un dépôt privé répond comme un dépôt absent ; un réseau en panne ou une limite de débit ne prouvent rien. Le
résultat est donc à trois états, et l'utilisateur garde la main : ajouter quand même reste possible.
"""

import logging
from enum import StrEnum
from typing import NamedTuple

import httpx

from src.orbi_dev.inputs import Repo

logger = logging.getLogger("orbi.dev.github")

API = "https://api.github.com/repos/{full_name}"
TIMEOUT = 5.0


class Lookup(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"  # absent, ou privé (GitHub répond pareil)
    UNKNOWN = "unknown"  # réseau, limite de débit, erreur côté GitHub


class RepoInfo(NamedTuple):
    state: Lookup
    default_branch: str = ""
    description: str = ""
    language: str = ""
    archived: bool = False


async def lookup_repo(repo: Repo, client: httpx.AsyncClient | None = None) -> RepoInfo:
    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False)
    try:
        response = await client.get(
            API.format(full_name=repo.full_name),
            headers={"Accept": "application/vnd.github+json", "User-Agent": "orbi-dev"},
        )
    except httpx.HTTPError as error:
        logger.info("Vérification GitHub impossible pour %s : %s", repo.full_name, type(error).__name__)
        return RepoInfo(Lookup.UNKNOWN)
    finally:
        if own:
            await client.aclose()

    if response.status_code == 404:
        return RepoInfo(Lookup.NOT_FOUND)
    if response.status_code != 200:
        return RepoInfo(Lookup.UNKNOWN)
    try:
        data = response.json()
    except ValueError:
        return RepoInfo(Lookup.UNKNOWN)
    if not isinstance(data, dict):
        return RepoInfo(Lookup.UNKNOWN)
    return RepoInfo(
        Lookup.FOUND,
        default_branch=str(data.get("default_branch") or "")[:100],
        description=str(data.get("description") or "")[:200],
        language=str(data.get("language") or "")[:40],
        archived=bool(data.get("archived")),
    )
