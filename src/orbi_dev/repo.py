"""
Orbi Dev — Lire une adresse de dépôt collée dans le chat.

Accepte ce qu'on copie vraiment : l'adresse de la page GitHub (avec ou sans `https://`, `.git`, `/` final, ou
`/tree/<branche>` quand on était sur une branche), ou le raccourci `proprietaire/depot`. Tout le reste est refusé :
le dépôt devient une URL https transmise à un fournisseur, elle ne doit jamais être deviné.
"""

import re
from typing import NamedTuple

_NAME = r"[A-Za-z0-9_.-]+"
_URL = re.compile(
    rf"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>{_NAME})/(?P<repo>{_NAME}?)(?:\.git)?"
    rf"(?:/tree/(?P<branch>[^\s?#]+))?/?(?:[?#]\S*)?$"
)
_SHORT = re.compile(rf"^(?P<owner>{_NAME})/(?P<repo>{_NAME}?)(?:\.git)?$")


class Repo(NamedTuple):
    name: str
    url: str
    branch: str  # "" = branche par défaut du dépôt


def parse_repo(text: str) -> Repo | None:
    text = text.strip()
    if not text or len(text) > 300:
        return None
    match = _URL.match(text) or _SHORT.match(text)
    if match is None:
        return None
    owner, repo = match.group("owner"), match.group("repo")
    if repo in {".", ".."} or owner in {".", ".."}:
        return None
    branch = (match.groupdict().get("branch") or "")[:100]
    return Repo(name=repo[:100], url=f"https://github.com/{owner}/{repo}", branch=branch)
