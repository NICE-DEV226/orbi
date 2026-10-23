"""
Orbi — Interface mobile de suivi Orbi Dev (ORBI-DEV-04).

Pages : tâches, nouvelle tâche, projets, intégrations, détail d'exécution (avec suivi en direct).
Accès réservé aux administrateurs authentifiés ; chaque ressource est filtrée par propriétaire.
Aucune action de déploiement n'existe dans cette interface.
"""

import logging
from datetime import UTC
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.models.user import User
from src.orbi_dev import runner, service
from src.orbi_dev.connectors.base import ConnectorError, ErrorCategory
from src.orbi_dev.connectors.registry import available_providers
from src.orbi_dev.crypto import SecretsNotConfiguredError
from src.orbi_dev.models import Execution
from src.orbi_dev.state import ACTIVE_STATUSES, ExecutionStatus, is_terminal
from src.web.auth import require_admin
from src.web.csrf import csrf_protect, csrf_token_for

logger = logging.getLogger("orbi.web.dev")

router = APIRouter(prefix="/dev", tags=["Orbi Dev"], include_in_schema=False)
templates = Jinja2Templates(directory="src/templates")

STATUS_LABELS = {
    ExecutionStatus.QUEUED: ("En file", "secondary"),
    ExecutionStatus.AWAITING_APPROVAL: ("En attente d'approbation", "info"),
    ExecutionStatus.RUNNING: ("En cours", "primary"),
    ExecutionStatus.SUCCEEDED: ("Terminée", "success"),
    ExecutionStatus.FAILED: ("Échec", "danger"),
    ExecutionStatus.CANCEL_REQUESTED: ("Annulation demandée", "warning"),
    ExecutionStatus.CANCELLED: ("Annulée", "secondary"),
    ExecutionStatus.TIMED_OUT: ("Délai dépassé", "danger"),
    ExecutionStatus.NEEDS_ATTENTION: ("À vérifier", "warning"),
}

ERROR_MESSAGES = {
    ErrorCategory.AUTH_INVALID: "Clé refusée par le fournisseur.",
    ErrorCategory.PERMISSION_DENIED: "Permissions insuffisantes chez le fournisseur.",
    ErrorCategory.PLAN_OR_QUOTA: "Plan ou quota insuffisant chez le fournisseur.",
    ErrorCategory.RATE_LIMITED: "Trop de requêtes, réessayez dans un instant.",
    ErrorCategory.UNAVAILABLE: "Fournisseur indisponible, réessayez plus tard.",
    ErrorCategory.TIMEOUT: "Le fournisseur n'a pas répondu à temps.",
    ErrorCategory.UNSUPPORTED_CAPABILITY: "Cette opération n'est pas supportée par le fournisseur.",
    ErrorCategory.INVALID_REQUEST: "Requête invalide.",
}


def safe_link(url: str | None) -> str | None:
    """Un lien fourni par un tiers n'est affiché que s'il est en https (jamais javascript:, data:…)."""
    return url if url and url.startswith("https://") and " " not in url else None


def fmt_dt(value) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%d/%m %H:%M UTC")


templates.env.filters["safe_link"] = safe_link
templates.env.filters["fmt_dt"] = fmt_dt
templates.env.globals["status_label"] = lambda s: STATUS_LABELS[ExecutionStatus(s)]
templates.env.globals["is_active_status"] = lambda s: ExecutionStatus(s) in ACTIVE_STATUSES | {ExecutionStatus.AWAITING_APPROVAL}


def render(request: Request, name: str, admin: User, **context: Any):
    context.update(admin=admin, csrf_token=csrf_token_for(request))
    return templates.TemplateResponse(request, name, context)


def not_found(request: Request, admin: User):
    return templates.TemplateResponse(
        request, "dev_notfound.html", {"admin": admin, "csrf_token": csrf_token_for(request), "active_nav": ""},
        status_code=404,
    )


def friendly(error: ConnectorError) -> str:
    return ERROR_MESSAGES.get(error.category, "Erreur du fournisseur.")


async def _launch_safely(owner_id: int, execution_id: str) -> None:
    try:
        await runner.launch_execution(owner_id, execution_id)
    except Exception:
        logger.exception("Lancement %s en échec", execution_id)


def execution_payload(execution: Execution, events: list) -> dict[str, Any]:
    return {
        "id": str(execution.id),
        "status": execution.status.value,
        "status_label": STATUS_LABELS[execution.status][0],
        "status_color": STATUS_LABELS[execution.status][1],
        "terminal": is_terminal(execution.status),
        "active": execution.status in ACTIVE_STATUSES or execution.status == ExecutionStatus.AWAITING_APPROVAL,
        "pr_url": safe_link(execution.pr_url),
        "branch": execution.branch,
        "external_url": safe_link(execution.external_url),
        "summary": execution.result_summary,
        "error_message": execution.error_message,
        "updated_at": fmt_dt(execution.updated_at),
        "events": [
            {"seq": e.seq, "message": e.message, "at": fmt_dt(e.created_at),
             "status_label": STATUS_LABELS[e.to_status][0] if e.to_status else ""}
            for e in events
        ],
    }


# ─────────────────────────────────────
# Tâches
# ─────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, admin: User = Depends(require_admin)):
    tasks = await service.list_tasks(admin.telegram_id)
    rows = []
    for task in tasks:
        executions = await service.list_executions(admin.telegram_id, task_id=str(task.id), limit=1)
        rows.append({"task": task, "execution": executions[0] if executions else None})
    return render(request, "dev_home.html", admin, rows=rows, active_nav="tasks")


@router.get("/tasks/new", response_class=HTMLResponse)
async def new_task_form(request: Request, admin: User = Depends(require_admin)):
    return await _new_task_page(request, admin)


async def _new_task_page(request: Request, admin: User, error: str | None = None, prompt: str = ""):
    projects = await service.list_projects(admin.telegram_id)
    integrations = [i for i in await service.list_integrations(admin.telegram_id) if i.status.value == "active"]
    return render(request, "dev_task_new.html", admin, projects=projects, integrations=integrations,
                  error=error, prompt=prompt, active_nav="new")


@router.post("/tasks", dependencies=[Depends(csrf_protect)])
async def create_task(
    request: Request, background: BackgroundTasks, admin: User = Depends(require_admin),
    project_id: str = Form(...), integration_id: str = Form(...), prompt: str = Form(...),
):
    prompt = prompt.strip()
    if not prompt or len(prompt) > 8000:
        return await _new_task_page(request, admin, "La description doit faire entre 1 et 8000 caractères.", prompt)
    try:
        task = await service.create_task(admin.telegram_id, project_id, integration_id, prompt)
        execution = await service.create_execution(admin.telegram_id, str(task.id))
    except service.NotFoundError:
        return await _new_task_page(request, admin, "Projet ou intégration introuvable.", prompt)
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

@router.get("/executions/{execution_id}", response_class=HTMLResponse)
async def execution_detail(execution_id: str, request: Request, admin: User = Depends(require_admin)):
    try:
        execution = await service.get_execution(admin.telegram_id, execution_id)
        task = await service.get_task(admin.telegram_id, execution.task_id)
        events = await service.list_events(admin.telegram_id, execution_id)
    except service.NotFoundError:
        return not_found(request, admin)
    return render(request, "dev_execution.html", admin, execution=execution, task=task,
                  data=execution_payload(execution, events), active_nav="tasks")


@router.get("/api/executions/{execution_id}")
async def execution_json(execution_id: str, admin: User = Depends(require_admin)):
    try:
        execution = await service.get_execution(admin.telegram_id, execution_id)
        events = await service.list_events(admin.telegram_id, execution_id)
    except service.NotFoundError:
        return JSONResponse({"detail": "introuvable"}, status_code=404)
    return JSONResponse(execution_payload(execution, events), headers={"Cache-Control": "no-store"})


@router.post("/executions/{execution_id}/refresh", dependencies=[Depends(csrf_protect)])
async def refresh(execution_id: str, request: Request, admin: User = Depends(require_admin)):
    try:
        await runner.refresh_execution(admin.telegram_id, execution_id)
    except service.NotFoundError:
        return not_found(request, admin)
    return RedirectResponse(f"/dev/executions/{execution_id}", status_code=303)


@router.post("/executions/{execution_id}/cancel", dependencies=[Depends(csrf_protect)])
async def cancel(execution_id: str, request: Request, admin: User = Depends(require_admin)):
    try:
        await runner.request_cancel(admin.telegram_id, execution_id)
    except service.NotFoundError:
        return not_found(request, admin)
    except (service.ConflictError, ConnectorError) as e:
        logger.info("Annulation refusée pour %s : %s", execution_id, type(e).__name__)
    return RedirectResponse(f"/dev/executions/{execution_id}", status_code=303)


# ─────────────────────────────────────
# Projets
# ─────────────────────────────────────

@router.get("/projects", response_class=HTMLResponse)
async def projects(request: Request, admin: User = Depends(require_admin)):
    return render(request, "dev_projects.html", admin, projects=await service.list_projects(admin.telegram_id),
                  error=None, active_nav="projects")


@router.post("/projects", dependencies=[Depends(csrf_protect)])
async def add_project(
    request: Request, admin: User = Depends(require_admin),
    name: str = Form(...), repo_url: str = Form(...), default_branch: str = Form("main"),
):
    try:
        await service.create_project(admin.telegram_id, name.strip(), repo_url.strip(), default_branch.strip() or "main")
    except ValueError:
        return render(request, "dev_projects.html", admin, projects=await service.list_projects(admin.telegram_id),
                      error="Nom (1-100 caractères) et URL https du dépôt requis.", active_nav="projects")
    return RedirectResponse("/dev/projects", status_code=303)


# ─────────────────────────────────────
# Intégrations
# ─────────────────────────────────────

async def _integrations_page(request: Request, admin: User, error: str | None = None):
    return render(request, "dev_integrations.html", admin,
                  integrations=await service.list_integrations(admin.telegram_id),
                  providers=available_providers(), error=error, active_nav="keys")


@router.get("/integrations", response_class=HTMLResponse)
async def integrations(request: Request, admin: User = Depends(require_admin)):
    return await _integrations_page(request, admin)


@router.post("/integrations", dependencies=[Depends(csrf_protect)])
async def connect(
    request: Request, admin: User = Depends(require_admin),
    provider: str = Form(...), api_key: str = Form(...), label: str = Form(""),
):
    try:
        await runner.connect_integration(admin.telegram_id, provider, api_key.strip(), label.strip()[:100])
    except ConnectorError as e:
        return await _integrations_page(request, admin, friendly(e))
    except SecretsNotConfiguredError:
        return await _integrations_page(request, admin, "Le chiffrement des secrets n'est pas configuré sur ce serveur.")
    return RedirectResponse("/dev/integrations", status_code=303)


@router.post("/integrations/{integration_id}/revoke", dependencies=[Depends(csrf_protect)])
async def revoke(integration_id: str, request: Request, admin: User = Depends(require_admin)):
    try:
        await runner.revoke_integration(admin.telegram_id, integration_id)
    except service.NotFoundError:
        return not_found(request, admin)
    return RedirectResponse("/dev/integrations", status_code=303)
