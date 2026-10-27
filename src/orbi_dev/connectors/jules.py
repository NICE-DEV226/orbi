"""
Orbi Dev — Connecteur Jules (Google) API v1alpha (docs/connectors/jules.md).

Écrit d'après la documentation officielle (https://developers.google.com/jules/api), consultée le 2026-10-27.
L'API est **alpha** (« expérimentale ») : voir docs/connectors/jules.md pour les hypothèses et ce qui n'a pas été
vérifié contre un compte réel.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

import httpx

from src.orbi_dev.connectors.base import (
    Capability,
    ConnectorError,
    ErrorCategory,
    LaunchRequest,
    RemoteRun,
    RemoteStatus,
    VerifyResult,
)
from src.orbi_dev.connectors.http import HttpConnector, parse_retry_after
from src.orbi_dev.redact import sanitize_text

logger = logging.getLogger("orbi.dev.jules")

DEFAULT_BASE_URL = "https://jules.googleapis.com"
API = "/v1alpha"

SOURCE_PAGE_SIZE = 100
MAX_SOURCE_PAGES = 20
ACTIVITY_PAGE_SIZE = 100
MAX_ACTIVITY_PAGES = 5
SESSION_PAGE_SIZE = 50
MAX_SESSION_PAGES = 3

_REPO_URL = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

_STATE_STATUS = {
    "QUEUED": RemoteStatus.PENDING,
    "PLANNING": RemoteStatus.RUNNING,
    "IN_PROGRESS": RemoteStatus.RUNNING,
    "AWAITING_PLAN_APPROVAL": RemoteStatus.WAITING,
    "AWAITING_USER_FEEDBACK": RemoteStatus.WAITING,
    "PAUSED": RemoteStatus.WAITING,
    "FAILED": RemoteStatus.FAILED,
    "COMPLETED": RemoteStatus.SUCCEEDED,
}

_WAITING_REASON = {
    "AWAITING_PLAN_APPROVAL": "Un plan attend votre approbation dans Jules.",
    "AWAITING_USER_FEEDBACK": "Jules attend votre réponse.",
    "PAUSED": "La session est en pause dans Jules.",
}

# google.rpc.Code, tel que renvoyé dans `error.status`
_GOOGLE_STATUS_CATEGORY = {
    "UNAUTHENTICATED": ErrorCategory.AUTH_INVALID,
    "PERMISSION_DENIED": ErrorCategory.PERMISSION_DENIED,
    "NOT_FOUND": ErrorCategory.NOT_FOUND,
    "INVALID_ARGUMENT": ErrorCategory.INVALID_REQUEST,
    "FAILED_PRECONDITION": ErrorCategory.INVALID_REQUEST,
    "OUT_OF_RANGE": ErrorCategory.INVALID_REQUEST,
    "ALREADY_EXISTS": ErrorCategory.CONFLICT,
    "ABORTED": ErrorCategory.CONFLICT,
    "RESOURCE_EXHAUSTED": ErrorCategory.PLAN_OR_QUOTA,
    "UNAVAILABLE": ErrorCategory.UNAVAILABLE,
    "INTERNAL": ErrorCategory.UNAVAILABLE,
    "DEADLINE_EXCEEDED": ErrorCategory.UNAVAILABLE,
}

_HTTP_CATEGORY = {
    400: ErrorCategory.INVALID_REQUEST,
    401: ErrorCategory.AUTH_INVALID,
    403: ErrorCategory.PERMISSION_DENIED,
    404: ErrorCategory.NOT_FOUND,
    409: ErrorCategory.CONFLICT,
    429: ErrorCategory.PLAN_OR_QUOTA,
}


def error_from_response(response: httpx.Response) -> ConnectorError:
    """Traduit une erreur Google (`{"error": {code, message, status, details}}`) sans reprendre de corps brut."""
    status_name = message = ""
    reasons: list[str] = []
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            status_name = error.get("status") if isinstance(error.get("status"), str) else ""
            message = error.get("message") if isinstance(error.get("message"), str) else ""
            reasons = [d["reason"] for d in error.get("details") or [] if isinstance(d, dict) and isinstance(d.get("reason"), str)]
    except ValueError:
        pass

    http = response.status_code
    # Google renvoie une clé invalide en 400 INVALID_ARGUMENT (reason API_KEY_INVALID), pas en 401.
    if "API_KEY_INVALID" in reasons or "api key not valid" in message.lower():
        category = ErrorCategory.AUTH_INVALID
    else:
        category = _GOOGLE_STATUS_CATEGORY.get(status_name) or _HTTP_CATEGORY.get(http)
    if category is None:
        category = ErrorCategory.UNAVAILABLE if http >= 500 else ErrorCategory.UNKNOWN
    retry_after = parse_retry_after(response.headers.get("retry-after"))
    if category == ErrorCategory.PLAN_OR_QUOTA and retry_after is not None:
        category = ErrorCategory.RATE_LIMITED  # un délai d'attente indiqué = limite de débit, pas un quota épuisé
    return ConnectorError(
        category,
        sanitize_text(message, 300) or f"Erreur du fournisseur (HTTP {http})",
        code=status_name or None,
        retryable=category in (ErrorCategory.RATE_LIMITED, ErrorCategory.UNAVAILABLE),
        retry_after=retry_after,
    )


_FATAL_LINE = re.compile(r"^\+*\s*(fatal|error):", re.IGNORECASE)


def summarize_failure(reason: str) -> str:
    """
    Raison d'échec lisible. Jules renvoie parfois un journal de script entier : on garde la phrase d'introduction et
    la dernière ligne `fatal:` / `error:` (la cause réelle), sans le bruit intermédiaire.
    """
    lines = [line.strip() for line in reason.replace("```", "\n").splitlines() if line.strip()]
    if not lines:
        return ""
    fatal = [line for line in lines[1:] if _FATAL_LINE.match(line)]
    return sanitize_text(f"{lines[0]} {fatal[-1]}" if fatal else lines[0], 500)


def _first_line(text: str, limit: int) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


class JulesConnector(HttpConnector):
    provider = "jules"
    display_name = "Jules"
    # Pas d'annulation : l'API v1alpha n'en documente aucune (voir docs/connectors/jules.md).
    capabilities = frozenset({Capability.LAUNCH, Capability.STATUS, Capability.PULL_REQUEST})

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 15.0,
        max_retries: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        super().__init__(
            base_url=base_url, headers={"X-Goog-Api-Key": api_key}, transport=transport, timeout=timeout,
            max_retries=max_retries, sleep=sleep,
        )

    def _error_from_response(self, response: httpx.Response) -> ConnectorError:
        return error_from_response(response)

    # ── contrat ──

    async def verify(self) -> VerifyResult:
        # Lecture seule : prouve que la clé est valide, sans créer de session.
        await self._request("GET", f"{API}/sources", params={"pageSize": 1})
        return VerifyResult(capabilities=self.capabilities)

    async def launch(self, request: LaunchRequest) -> RemoteRun:
        source, branch = await self._source_for(request.repo_url, request.base_branch)
        body = {
            "prompt": request.prompt,
            "title": f"{_first_line(request.prompt, 60)} {self._marker(request.client_ref)}".strip(),
            "sourceContext": {"source": source, "githubRepoContext": {"startingBranch": branch}},
            "automationMode": "AUTO_CREATE_PR",
        }
        # Pas d'identifiant choisi par le client : jamais de nouvel essai après un délai dépassé (risque de doublon).
        # Si la réponse est perdue, le runner appelle find_by_client_ref().
        session = await self._request("POST", f"{API}/sessions", json=body)
        return self._to_remote(session)

    async def get(self, external_id: str) -> RemoteRun:
        session = await self._request("GET", f"{API}/sessions/{self._session_id(external_id)}")
        remote = self._to_remote(session)
        state = str(session.get("state", ""))
        if state in ("COMPLETED", "FAILED", "AWAITING_USER_FEEDBACK"):
            remote = await self._with_activity_details(remote, session)
        return remote

    async def find_by_client_ref(self, client_ref: str) -> RemoteRun | None:
        marker = self._marker(client_ref)
        token: str | None = None
        for _ in range(MAX_SESSION_PAGES):
            params: dict[str, Any] = {"pageSize": SESSION_PAGE_SIZE}
            if token:
                params["pageToken"] = token
            page = await self._request("GET", f"{API}/sessions", params=params)
            for session in page.get("sessions") or []:
                if isinstance(session, dict) and marker in str(session.get("title", "")):
                    return self._to_remote(session)
            token = page.get("nextPageToken")
            if not token:
                break
        return None

    # ── dépôt ──

    @staticmethod
    def _marker(client_ref: str) -> str:
        return f"[orbi:{client_ref}]"

    @staticmethod
    def _session_id(external_id: str) -> str:
        if not _SESSION_ID.fullmatch(external_id):
            raise ConnectorError(ErrorCategory.INVALID_REQUEST, "Identifiant de session invalide")
        return external_id

    async def _source_for(self, repo_url: str, base_branch: str) -> tuple[str, str]:
        """
        Nom de la source Jules (`sources/...`) du dépôt, et branche de départ à utiliser.

        Le dépôt doit être connecté à Jules par l'application GitHub. Une branche vide prend la branche par défaut du
        dépôt ; une branche que Jules ne connaît pas est refusée ici, avant de créer une session vouée à l'échec.
        """
        match = _REPO_URL.fullmatch(repo_url.strip())
        if not match:
            raise ConnectorError(ErrorCategory.INVALID_REQUEST, "Jules ne prend en charge que les dépôts GitHub")
        owner, repo = (part.lower() for part in match.groups())
        full_name = f"{match.group(1)}/{match.group(2).removesuffix('.git')}"
        token: str | None = None
        for _ in range(MAX_SOURCE_PAGES):
            params: dict[str, Any] = {"pageSize": SOURCE_PAGE_SIZE}
            if token:
                params["pageToken"] = token
            page = await self._request("GET", f"{API}/sources", params=params)
            for source in page.get("sources") or []:
                github = source.get("githubRepo") if isinstance(source, dict) else None
                if (
                    isinstance(github, dict)
                    and str(github.get("owner", "")).lower() == owner
                    and str(github.get("repo", "")).lower() == repo.removesuffix(".git")
                    and isinstance(source.get("name"), str)
                ):
                    return source["name"], self._choose_branch(github, base_branch.strip(), full_name)
            token = page.get("nextPageToken")
            if not token:
                break
        raise ConnectorError(
            ErrorCategory.PERMISSION_DENIED,
            f"Ce dépôt n'est pas connecté à Jules : installez l'application GitHub de Jules sur « {full_name} ».",
            code="repository_access",
        )

    @staticmethod
    def _choose_branch(github: dict[str, Any], wanted: str, full_name: str) -> str:
        def name(branch: Any) -> str:
            return str(branch.get("displayName", "")) if isinstance(branch, dict) else ""

        default = name(github.get("defaultBranch"))
        known = [n for n in (name(b) for b in github.get("branches") or []) if n]
        if not wanted:
            if default:
                return default
            raise ConnectorError(
                ErrorCategory.INVALID_REQUEST,
                f"Indiquez la branche de départ du projet : Jules n'a pas fourni la branche par défaut de « {full_name} ».",
                code="branch_required",
            )
        if known and wanted not in known:
            listed = ", ".join(f"« {n} »" for n in known[:8]) + ("…" if len(known) > 8 else "")
            raise ConnectorError(
                ErrorCategory.INVALID_REQUEST,
                f"La branche « {wanted} » n'existe pas (ou n'est pas active) dans « {full_name} ». "
                f"Branches connues de Jules : {listed}. Corrigez la branche du projet, ou laissez-la vide.",
                code="branch_not_found",
            )
        return wanted

    # ── détails (activités) ──

    async def _activities(self, session_id: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        token: str | None = None
        for _ in range(MAX_ACTIVITY_PAGES):
            params: dict[str, Any] = {"pageSize": ACTIVITY_PAGE_SIZE}
            if token:
                params["pageToken"] = token
            page = await self._request("GET", f"{API}/sessions/{session_id}/activities", params=params)
            found += [a for a in page.get("activities") or [] if isinstance(a, dict)]
            token = page.get("nextPageToken")
            if not token:
                break
        return found

    async def _with_activity_details(self, remote: RemoteRun, session: dict[str, Any]) -> RemoteRun:
        """Complète le résultat avec la raison d'un échec ou le dernier message de l'agent. Au mieux : sans effet si ça échoue."""
        try:
            activities = await self._activities(remote.external_id)
        except ConnectorError as e:
            logger.info("Activités Jules illisibles (%s) : état conservé sans détail", e.category)
            return remote

        def last(key: str) -> dict[str, Any] | None:
            items = [a for a in activities if key in a]
            return max(items, key=lambda a: str(a.get("createTime", ""))) if items else None

        state = session.get("state")
        if state == "FAILED":
            failed = last("sessionFailed")
            reason = ((failed or {}).get("sessionFailed") or {}).get("reason")
            if isinstance(reason, str) and reason.strip():
                return replace(remote, error_message=summarize_failure(reason))
        elif state == "AWAITING_USER_FEEDBACK":
            message = ((last("agentMessaged") or {}).get("agentMessaged") or {}).get("agentMessage")
            if isinstance(message, str) and message.strip():
                return replace(
                    remote, error_message=sanitize_text(f"{_WAITING_REASON['AWAITING_USER_FEEDBACK']} {message}", 500)
                )
        elif state == "COMPLETED" and not remote.summary:
            message = ((last("agentMessaged") or {}).get("agentMessaged") or {}).get("agentMessage")
            if isinstance(message, str) and message.strip():
                return replace(remote, summary=sanitize_text(message, 1000))
        return remote

    # ── mapping ──

    @staticmethod
    def _to_remote(session: dict[str, Any]) -> RemoteRun:
        state = str(session.get("state", ""))
        status = _STATE_STATUS.get(state)
        if status is None:
            logger.info("État Jules inconnu %r : traité comme en attente", state)
            status = RemoteStatus.PENDING

        pr_url = pr_title = None
        for output in session.get("outputs") or []:
            pr = output.get("pullRequest") if isinstance(output, dict) else None
            if isinstance(pr, dict) and pr.get("url"):
                pr_url, pr_title = pr["url"], pr.get("title")
                break

        session_id = session.get("id") or str(session.get("name", "")).removeprefix("sessions/")
        summary = sanitize_text(pr_title, 300) if status == RemoteStatus.SUCCEEDED and isinstance(pr_title, str) else None
        error = None
        if status == RemoteStatus.WAITING:
            error = _WAITING_REASON.get(state)
        elif status == RemoteStatus.FAILED:
            error = "La session a échoué chez Jules."
        return RemoteRun(
            status=status,
            external_id=session_id,
            external_url=session.get("url"),
            summary=summary,
            branch=None,  # l'API n'expose pas le nom de branche
            pr_url=pr_url,
            error_message=error,
        )
