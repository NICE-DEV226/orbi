"""
Orbi Dev — Lire et nettoyer ce que l'utilisateur colle ou écrit (dépôt, branche, nom, consigne).

Une seule définition de « valide », utilisée par le bot, le web et les modèles. Le dépôt devient une URL https transmise
à un fournisseur, la branche un argument git : rien n'est deviné, tout ce qui sort du format est refusé avec une raison.
"""

import re
from typing import NamedTuple

_NAME = r"[A-Za-z0-9_.-]+"
_URL = re.compile(
    rf"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>{_NAME})/(?P<repo>{_NAME}?)(?:\.git)?"
    rf"(?:/tree/(?P<branch>[^\s?#]+))?/?(?:[?#]\S*)?$"
)
_SHORT = re.compile(rf"^(?P<owner>{_NAME})/(?P<repo>{_NAME}?)(?:\.git)?$")
_TRIM = "<>()[]{}\"'`.,;:!?"

MIN_PROMPT = 5
MAX_PROMPT = 8000
MAX_NAME = 60

# Caractères de contrôle (sauf retour à la ligne et tabulation) : jamais dans une consigne ni un nom
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")


class Repo(NamedTuple):
    name: str
    url: str
    branch: str  # "" = branche par défaut du dépôt

    @property
    def full_name(self) -> str:
        return self.url.removeprefix("https://github.com/")


def _from_match(match: re.Match) -> Repo | None:
    owner, repo = match.group("owner"), match.group("repo")
    if repo in {".", ".."} or owner in {".", ".."}:
        return None
    branch = (match.groupdict().get("branch") or "")[:100]
    return Repo(name=repo[:100], url=f"https://github.com/{owner}/{repo}", branch=branch)


def parse_repo(text: str) -> Repo | None:
    """Le texte entier est un dépôt (adresse ou `proprietaire/depot`), ou une adresse GitHub se cache dans une phrase."""
    text = text.strip()
    if not text or len(text) > 2000:
        return None
    if len(text) <= 300:
        match = _URL.match(text) or _SHORT.match(text)
        if match:
            return _from_match(match)
    for token in text.split():
        match = _URL.match(token.strip(_TRIM))
        if match:
            return _from_match(match)
    return None


# Règles git des noms de branche, version prudente : jamais d'espace, de « .. », de « @{ », ni de tiret en tête
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+-]{0,99}$")
DEFAULT_BRANCH_WORDS = {"-", "défaut", "defaut", "default", "par défaut", "par defaut"}


def valid_branch(name: str) -> bool:
    return (
        bool(_BRANCH.match(name))
        and ".." not in name and "//" not in name
        and not name.endswith(("/", ".", ".lock"))
    )


def parse_branch(text: str) -> str | None:
    """'' = branche par défaut du dépôt ; None si le texte n'est pas un nom de branche acceptable."""
    text = text.strip()
    if text.lower() in DEFAULT_BRANCH_WORDS:
        return ""
    return text if valid_branch(text) else None


def clean_text(text: str) -> str:
    """Retire les caractères de contrôle et les lignes vides en excès ; garde le texte lisible tel qu'écrit."""
    text = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_name(text: str) -> str | None:
    """Nom d'affichage d'un projet : une ligne, 1 à 60 caractères."""
    text = clean_text(text)
    if not text or "\n" in text or len(text) > MAX_NAME:
        return None
    return text
