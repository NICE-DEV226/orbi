"""
Orbi — Couche d'interface commune (rendu serveur Jinja + htmx).

Une seule enveloppe (`layout.html`) pour tout le web : Orbi Dev et l'administration. Ce module regroupe ce que toutes
les pages partagent : environnement de gabarits, filtres, libellés d'état, navigation et aides htmx.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.models.user import User
from src.orbi_dev.present import PROVIDER_NAMES, STATUS_INFO, ago, aware, provider_name  # noqa: F401 (réexportés)
from src.orbi_dev.state import ExecutionStatus
from src.web.csrf import csrf_token_for

templates = Jinja2Templates(directory="src/templates")

# ─────────────────────────────────────
# États d'exécution : vocabulaire de l'interface
# ─────────────────────────────────────

S = ExecutionStatus

ACTIVE_GROUPS = ("attention", "active", "done")
GROUP_TITLES = {"attention": "À vérifier", "active": "En cours", "done": "Récentes"}


TONE_VAR = {"orbit": "--orbite", "ok": "--ok", "bad": "--bad", "signal": "--signal", "muted": "--brume"}


def status_info(status: ExecutionStatus | str) -> dict[str, str]:
    label, sentence, tone, group = STATUS_INFO[ExecutionStatus(status)]
    return {
        "value": ExecutionStatus(status).value, "label": label, "sentence": sentence, "tone": tone, "group": group,
        "var": TONE_VAR[tone],
    }


# ─────────────────────────────────────
# Filtres
# ─────────────────────────────────────

def duration(start: datetime | None, end: datetime | None = None) -> str:
    """Durée entre deux instants (« 4 min », « 1 h 12 »)."""
    start, end = aware(start), aware(end) or datetime.now(UTC)
    if start is None:
        return ""
    seconds = max(int((end - start).total_seconds()), 0)
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d}"


def fmt_dt(value: datetime | None) -> str:
    value = aware(value)
    return value.strftime("%d/%m/%Y %H:%M UTC") if value else ""


def safe_link(url: str | None) -> str | None:
    """Un lien fourni par un tiers n'est affiché que s'il est en https (jamais javascript:, data:…)."""
    return url if url and url.startswith("https://") and " " not in url else None


def repo_label(url: str) -> str:
    """https://github.com/acme/orbi-api -> acme/orbi-api"""
    return url.removeprefix("https://").split("/", 1)[-1] if "/" in url.removeprefix("https://") else url


# Où trouver la clé et ce qu'il faut avoir fait avant (affiché sous le formulaire de connexion)
PROVIDER_HELP = {
    "cursor": "Clé d'API créée dans le tableau de bord Cursor (de préférence un compte de service).",
    "jules": "Clé créée dans les réglages de Jules (jules.google.com), puis application GitHub de Jules installée sur chaque dépôt à confier.",
}
CAPABILITY_WORDS = {
    "launch": "lancer des tâches", "status": "suivre leur avancement", "cancel": "les annuler",
    "pull_request": "proposer une pull request",
}


def capabilities(values: list[str]) -> str:
    """['launch', 'status'] -> « lancer des tâches et suivre leur avancement »"""
    words = [CAPABILITY_WORDS.get(v, v) for v in values]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " et " + words[-1] if words else ""


templates.env.filters.update({
    "ago": ago, "duration": duration, "fmt_dt": fmt_dt, "safe_link": safe_link, "repo": repo_label,
    "provider_name": provider_name, "capabilities": capabilities,
})
templates.env.globals["status_info"] = status_info
templates.env.globals["PROVIDER_HELP"] = PROVIDER_HELP
templates.env.globals["GROUP_TITLES"] = GROUP_TITLES

# ─────────────────────────────────────
# Navigation
# ─────────────────────────────────────

def _item(key: str, label: str, href: str, icon: str) -> dict[str, str]:
    return {"key": key, "label": label, "href": href, "icon": icon}


# Barre du bas sur téléphone : 4 entrées. « Réglages » regroupe les pages secondaires.
TAB_ITEMS = [
    _item("runs", "Tâches", "/dev/", "tasks"),
    _item("projects", "Projets", "/dev/projects", "folder"),
    _item("tickets", "Support", "/admin/tickets", "headset"),
    _item("settings", "Réglages", "/admin/", "sliders"),
]
SETTINGS_CHILDREN = ("settings", "connections", "users", "system")

# Colonne de gauche sur ordinateur : tout est directement accessible.
RAIL_ITEMS = [
    _item("runs", "Tâches", "/dev/", "tasks"),
    _item("projects", "Projets", "/dev/projects", "folder"),
    _item("connections", "Connexions", "/dev/integrations", "key"),
    _item("tickets", "Support", "/admin/tickets", "headset"),
    _item("users", "Utilisateurs", "/admin/users", "users"),
    _item("system", "Système", "/admin/system", "pulse"),
]

# Version des ressources statiques : change à chaque modification du CSS (évite un cache périmé).
try:
    ASSET_VERSION = str(int(Path("src/static/orbi.css").stat().st_mtime))
except OSError:  # pragma: no cover
    ASSET_VERSION = "0"


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def htmx_target(request: Request) -> str:
    return request.headers.get("hx-target", "")


def render(request: Request, name: str, admin: User, *, status_code: int = 200, section: str = "", **context: Any):
    """Rend une page dans l'enveloppe commune (ou un fragment htmx)."""
    context.update(
        admin=admin, csrf_token=csrf_token_for(request), section=section, tabs=TAB_ITEMS, rail=RAIL_ITEMS,
        settings_children=SETTINGS_CHILDREN, asset_v=ASSET_VERSION,
    )
    response = templates.TemplateResponse(request, name, context, status_code=status_code)
    response.headers["Cache-Control"] = "no-store"  # contenu authentifié : ni cache partagé, ni cache de retour arrière
    return response
