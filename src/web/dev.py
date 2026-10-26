"""
Orbi — Orbi Dev : tâches, exécutions, projets et connexions (rendu serveur + htmx).

Accès réservé aux administrateurs authentifiés ; chaque ressource est filtrée par propriétaire.
Aucune action de déploiement n'existe dans cette interface. Les mises à jour en direct sont des fragments htmx :
ils se rafraîchissent seuls tant qu'une exécution est active, puis cessent de s'interroger.
"""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.models.user import User
from src.orbi_dev import runner, service
from src.orbi_dev.connectors.base import ConnectorError, ErrorCategory
from src.orbi_dev.connectors.registry import available_providers
from src.orbi_dev.crypto import SecretsNotConfiguredError
from src.orbi_dev.models import Execution
from src.orbi_dev.state import ACTIVE_STATUSES, ExecutionStatus, is_terminal
from src.web.auth import require_admin
from src.web.csrf import csrf_protect
from src.web.ui import ACTIVE_GROUPS, is_htmx, render, status_info

logger = logging.getLogger("orbi.web.dev")

router = APIRouter(prefix="/dev", tags=["Orbi Dev"], include_in_schema=False)

ERROR_MESSAGES = {
    ErrorCategory.AUTH_INVALID: "Le fournisseur a refusé cette clé.",
    ErrorCategory.PERMISSION_DENIED: "La clé n'a pas les permissions nécessaires chez le fournisseur.",
    ErrorCategory.PLAN_OR_QUOTA: "Le plan ou le quota du fournisseur ne permet pas cette opération.",
    ErrorCategory.RATE_LIMITED: "Trop de requêtes : réessayez dans un instant.",
    ErrorCategory.UNAVAILABLE: "Le fournisseur est indisponible : réessayez plus tard.",
    ErrorCategory.TIMEOUT: "Le fournisseur n'a pas répondu à temps.",
    ErrorCategory.UNSUPPORTED_CAPABILITY: "Le fournisseur ne propose pas cette opération.",
    ErrorCategory.INVALID_REQUEST: "Requête invalide.",
}

def friendly(error: ConnectorError) -> str:
    return ERROR_MESSAGES.get(error.category, "Erreur du fournisseur.")


def not_found(request: Request, admin: User):
    return render(request, "notfound.html", admin, status_code=404)


async def _launch_safely(owner_id: int, execution_id: str) -> None:
    try:
        await runner.launch_execution(owner_id, execution_id)
    except Exception:
        logger.exception("Lancement %s en échec", execution_id)


# ─────────────────────────────────────
# Tâches
# ─────────────────────────────────────

async def _runs_context(owner_id: int) -> dict[str, Any]:
    tasks = await service.list_tasks(owner_id)
    projects = {str(p.id): p for p in await service.list_projects(owner_id)}
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in ACTIVE_GROUPS}
    for task in tasks:
        executions = await service.list_executions(owner_id, task_id=str(task.id), limit=1)
        if not executions:
            continue
        execution = executions[0]
        project = projects.get(task.project_id)
        grouped[status_info(execution.status)["group"]].append(
            {"task": task, "execution": execution, "project": project.name if project else "projet supprimé"}
        )
    groups = [(key, grouped[key]) for key in ACTIVE_GROUPS if grouped[key]]
    polling = bool(grouped["active"] or grouped["attention"])

    parts = []
    if grouped["active"]:
        parts.append(f"{len(grouped['active'])} en cours")
    if grouped["attention"]:
        parts.append(f"{len(grouped['attention'])} à vérifier")
    summary = ", ".join(parts) if parts else ("Aucune exécution en cours" if tasks else "Rien pour l'instant")

    return {
        "groups": groups, "polling": polling, "summary": summary,
        "has_projects": bool(projects), "has_connections": any(i.status.value == "active" for i in await service.list_integrations(owner_id)),
    }


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, admin: User = Depends(require_admin)):
    return render(request, "runs/index.html", admin, section="runs", **await _runs_context(admin.telegram_id))


@router.get("/runs", response_class=HTMLResponse)
async def runs_fragment(request: Request, admin: User = Depends(require_admin)):
    """Fragment de la liste, interrogé par la page tant que des exécutions sont actives."""
    return render(request, "runs/_list.html", admin, **await _runs_context(admin.telegram_id))


async def _new_task_page(request: Request, admin: User, error: str | None = None, prompt: str = ""):
    projects = await service.list_projects(admin.telegram_id)
    integrations = [i for i in await service.list_integrations(admin.telegram_id) if i.status.value == "active"]
    return render(request, "runs/new.html", admin, section="runs", projects=projects, integrations=integrations,
                  error=error, prompt=prompt)


@router.get("/tasks/new", response_class=HTMLResponse)
async def new_task_form(request: Request, admin: User = Depends(require_admin)):
    return await _new_task_page(request, admin)


@router.post("/tasks", dependencies=[Depends(csrf_protect)])
async def create_task(
    request: Request, background: BackgroundTasks, admin: User = Depends(require_admin),
    project_id: str = Form(...), integration_id: str = Form(...), prompt: str = Form(...),
):
    prompt = prompt.strip()
    if not prompt or len(prompt) > 8000:
        return await _new_task_page(request, admin, "Décrivez la tâche en 8000 caractères au plus.", prompt)
    try:
        task = await service.create_task(admin.telegram_id, project_id, integration_id, prompt)
        execution = await service.create_execution(admin.telegram_id, str(task.id))
    except service.NotFoundError:
        return await _new_task_page(request, admin, "Ce projet ou cette connexion n'existe plus.", prompt)
    except service.ConflictError as e:
        return await _new_task_page(request, admin, str(e), prompt)
    background.add_task(_launch_safely, admin.telegram_id, str(execution.id))
    return RedirectResponse(f"/dev/executions/{execution.id}", status_code=303)


@router.post("/tasks/{task_id}/retry", dependencies=[Depends(csrf_protect)])
async def retry_task(task_id: str, background: BackgroundTasks, request: Request, admin: User = Depends(require_admin)):
    try:
        execution = await service.create_execution(admin.telegram_id, task_id)
    except service.NotFoundError:
        return not_found(request, admin)
    except service.ConflictError:
        return RedirectResponse("/dev/", status_code=303)
    background.add_task(_launch_safely, admin.telegram_id, str(execution.id))
    return RedirectResponse(f"/dev/executions/{execution.id}", status_code=303)


# ─────────────────────────────────────
# Exécutions
# ─────────────────────────────────────

async def _panel_context(admin: User, execution_id: str) -> dict[str, Any]:
    execution: Execution = await service.get_execution(admin.telegram_id, execution_id)
    task = await service.get_task(admin.telegram_id, execution.task_id)
    events = await service.list_events(admin.telegram_id, execution_id)
    try:
        project = (await service.get_project(admin.telegram_id, task.project_id)).name
    except service.NotFoundError:
        project = "projet supprimé"
    return {
        "execution": execution, "task": task, "project": project, "events": list(reversed(events)),
        "active": execution.status in ACTIVE_STATUSES or execution.status == ExecutionStatus.AWAITING_APPROVAL,
        "terminal": is_terminal(execution.status), "node_var": status_info(execution.status)["var"],
    }


@router.get("/executions/{execution_id}", response_class=HTMLResponse)
async def execution_detail(execution_id: str, request: Request, admin: User = Depends(require_admin)):
    try:
        context = await _panel_context(admin, execution_id)
    except service.NotFoundError:
        return not_found(request, admin)
    return render(request, "runs/detail.html", admin, section="runs", **context)


@router.get("/executions/{execution_id}/panel", response_class=HTMLResponse)
async def execution_panel(execution_id: str, request: Request, admin: User = Depends(require_admin)):
    """Fragment du panneau : interrogé par la page tant que l'exécution est active (se tait ensuite)."""
    try:
        context = await _panel_context(admin, execution_id)
    except service.NotFoundError:
        return not_found(request, admin)
    return render(request, "runs/_panel.html", admin, **context)


async def _after_action(request: Request, admin: User, execution_id: str):
    """Après une action : le fragment mis à jour pour htmx, sinon retour sur la page."""
    if not is_htmx(request):
        return RedirectResponse(f"/dev/executions/{execution_id}", status_code=303)
    return render(request, "runs/_panel.html", admin, **await _panel_context(admin, execution_id))


@router.post("/executions/{execution_id}/refresh", dependencies=[Depends(csrf_protect)])
async def refresh(execution_id: str, request: Request, admin: User = Depends(require_admin)):
    try:
        await runner.refresh_execution(admin.telegram_id, execution_id)
        return await _after_action(request, admin, execution_id)
    except service.NotFoundError:
        return not_found(request, admin)


@router.post("/executions/{execution_id}/cancel", dependencies=[Depends(csrf_protect)])
async def cancel(execution_id: str, request: Request, admin: User = Depends(require_admin)):
    try:
        await runner.request_cancel(admin.telegram_id, execution_id)
    except service.NotFoundError:
        return not_found(request, admin)
    except (service.ConflictError, ConnectorError) as e:
        logger.info("Annulation refusée pour %s : %s", execution_id, type(e).__name__)
    return await _after_action(request, admin, execution_id)


# ─────────────────────────────────────
# Projets
# ─────────────────────────────────────

async def _projects_page(request: Request, admin: User, error: str | None = None):
    return render(request, "projects.html", admin, section="projects",
                  projects=await service.list_projects(admin.telegram_id), error=error)


@router.get("/projects", response_class=HTMLResponse)
async def projects(request: Request, admin: User = Depends(require_admin)):
    return await _projects_page(request, admin)


@router.post("/projects", dependencies=[Depends(csrf_protect)])
async def add_project(
    request: Request, admin: User = Depends(require_admin),
    name: str = Form(...), repo_url: str = Form(...), default_branch: str = Form("main"),
):
    try:
        await service.create_project(admin.telegram_id, name.strip(), repo_url.strip(), default_branch.strip() or "main")
    except ValueError:
        return await _projects_page(request, admin, "Donnez un nom (100 caractères au plus) et une adresse de dépôt en https.")
    return RedirectResponse("/dev/projects", status_code=303)


# ─────────────────────────────────────
# Connexions (fournisseurs)
# ─────────────────────────────────────

async def _connections_page(request: Request, admin: User, error: str | None = None):
    return render(request, "connections.html", admin, section="connections",
                  integrations=await service.list_integrations(admin.telegram_id),
                  providers=available_providers(), error=error)


@router.get("/integrations", response_class=HTMLResponse)
async def integrations(request: Request, admin: User = Depends(require_admin)):
    return await _connections_page(request, admin)


@router.post("/integrations", dependencies=[Depends(csrf_protect)])
async def connect(
    request: Request, admin: User = Depends(require_admin),
    provider: str = Form(...), api_key: str = Form(...), label: str = Form(""),
):
    try:
        await runner.connect_integration(admin.telegram_id, provider, api_key.strip(), label.strip()[:100])
    except ConnectorError as e:
        return await _connections_page(request, admin, friendly(e))
    except SecretsNotConfiguredError:
        return await _connections_page(
            request, admin, "Le chiffrement des clés n'est pas configuré sur ce serveur (SECRETS_ENCRYPTION_KEY)."
        )
    return RedirectResponse("/dev/integrations", status_code=303)


@router.post("/integrations/{integration_id}/revoke", dependencies=[Depends(csrf_protect)])
async def revoke(integration_id: str, request: Request, admin: User = Depends(require_admin)):
    try:
        await runner.revoke_integration(admin.telegram_id, integration_id)
    except service.NotFoundError:
        return not_found(request, admin)
    return RedirectResponse("/dev/integrations", status_code=303)

