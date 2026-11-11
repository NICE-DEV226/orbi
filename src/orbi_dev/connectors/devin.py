"""
Orbi Dev — Connecteur Devin API v3 (docs/connectors/devin.md).

Écrit d'après la spécification OpenAPI officielle (https://docs.devin.ai/api-reference/v3), consultée le
2026-11-10. L'API exige une organisation (`org-…`) dans le chemin : le connecteur la découvre via
`GET /v3/self`, qui la renvoie pour les clés de service comme pour les jetons personnels — la clé seule
suffit donc comme secret d'intégration.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
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

logger = logging.getLogger("orbi.dev.devin")

DEFAULT_BASE_URL = "https://api.devin.ai"
API = "/v3"
WEB_SESSION_URL = "https://app.devin.ai/sessions/"

_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ORG_ID = re.compile(r"^org-[A-Za-z0-9_-]{1,100}$")

# Devin n'a pas d'état « cancelled » : DELETE termine la session, on le traduit en CANCELLED.
_STATUS = {
    "new": RemoteStatus.PENDING,
    "claimed": RemoteStatus.PENDING,
    "running": RemoteStatus.RUNNING,
    "resuming": RemoteStatus.RUNNING,
    "exit": RemoteStatus.SUCCEEDED,
    "error": RemoteStatus.FAILED,
    "suspended": RemoteStatus.WAITING,
}

# `status_detail` précise un `running` : la session attend une réponse ou une approbation de l'utilisateur.
_WAITING_DETAILS = {"waiting_for_user", "waiting_for_approval", "inactivity", "user_request"}

_HTTP_CATEGORY = {
    400: ErrorCategory.INVALID_REQUEST,
    401: ErrorCategory.AUTH_INVALID,
    403: ErrorCategory.PERMISSION_DENIED,
    404: ErrorCategory.NOT_FOUND,
    409: ErrorCategory.CONFLICT,
    410: ErrorCategory.NOT_FOUND,  # Gone : session supprimée ou expirée
    422: ErrorCategory.INVALID_REQUEST,
    429: ErrorCategory.RATE_LIMITED,
}

_CODE_CATEGORY = {
    "user_frozen": ErrorCategory.PERMISSION_DENIED,
    "migrated_session": ErrorCategory.CONFLICT,
}


def error_from_response(response: httpx.Response) -> ConnectorError:
    """Traduit un ProblemDetail RFC 9457 (`title`, `detail`, `error_code`) sans corps brut ni secret."""
    detail = title = code = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            # Compat ascendante : l'ancienne API renvoyait {"detail": ...} en corps entier.
            detail = body.get("detail") if isinstance(body.get("detail"), str) else ""
            title = body.get("title") if isinstance(body.get("title"), str) else ""
            code = body.get("error_code") if isinstance(body.get("error_code"), str) else ""
    except ValueError:
        pass

    http = response.status_code
    category = _CODE_CATEGORY.get(code) or _HTTP_CATEGORY.get(http)
    if category is None:
        category = ErrorCategory.UNAVAILABLE if http >= 500 else ErrorCategory.UNKNOWN
    return ConnectorError(
        category,
        sanitize_text(detail or title, 300) or f"Erreur du fournisseur (HTTP {http})",
        code=code or None,
        retryable=category in (ErrorCategory.RATE_LIMITED, ErrorCategory.UNAVAILABLE),
        retry_after=parse_retry_after(response.headers.get("retry-after")),
    )


class DevinConnector(HttpConnector):
    provider = "devin"
    display_name = "Devin"
    capabilities = frozenset(
        {Capability.LAUNCH, Capability.STATUS, Capability.CANCEL, Capability.PULL_REQUEST, Capability.INTERACT}
    )

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
            base_url=base_url, headers={"Authorization": f"Bearer {api_key}"}, transport=transport,
            timeout=timeout, max_retries=max_retries, sleep=sleep,
        )
        self._org_id: str | None = None

    def _error_from_response(self, response: httpx.Response) -> ConnectorError:
        return error_from_response(response)

    # ── organisation ──

    async def _org(self) -> str:
        """Org sous laquelle les sessions Devin de cette clé s'exécutent, découverte une fois par instance."""
        if self._org_id:
            return self._org_id
        self_info = await self._request("GET", f"{API}/self")
        org = (
            self_info.get("devin_sessions_org_id")
            or self_info.get("org_id")
            or self_info.get("primary_billing_org_id")
        )
        if not isinstance(org, str) or not _ORG_ID.fullmatch(org):
            raise ConnectorError(
                ErrorCategory.PERMISSION_DENIED,
                "Cette clé Devin n'est rattachée à aucune organisation utilisable pour les sessions.",
            )
        self._org_id = org
        return org

    def _org_path(self, org: str, suffix: str = "") -> str:
        return f"{API}/organizations/{org}{suffix}"

    @staticmethod
    def _session_id(external_id: str) -> str:
        if not _SESSION_ID.fullmatch(external_id):
            raise ConnectorError(ErrorCategory.INVALID_REQUEST, "Identifiant de session invalide")
        return external_id

    # ── contrat ──

    async def verify(self) -> VerifyResult:
        # GET /v3/self prouve la clé sans créer de session ni consommer d'ACU.
        await self._request("GET", f"{API}/self")
        return VerifyResult(capabilities=self.capabilities)

    def external_id_for(self, client_ref: str) -> str | None:
        # L'API accepte `devin_id` à la création : identifiant déterministe, comme `agentId` chez Cursor.
        return f"devin-{client_ref}"

    async def launch(self, request: LaunchRequest) -> RemoteRun:
        org = await self._org()
        devin_id = self.external_id_for(request.client_ref)
        body: dict[str, Any] = {"prompt": request.prompt}
        if request.repo_url:
            body["repos"] = [request.repo_url]
        data = await self._request(
            "POST", self._org_path(org, "/sessions"), params={"devin_id": devin_id}, json=body,
            retry_unknown=True,  # devin_id choisi : rejouer le même POST ne crée pas de doublon
        )
        return self._to_remote(data, fallback_id=devin_id or "")

    async def get(self, external_id: str) -> RemoteRun:
        session_id = self._session_id(external_id)
        org = await self._org()
        data = await self._request("GET", self._org_path(org, f"/sessions/{session_id}"))
        return self._to_remote(data, fallback_id=session_id)

    async def cancel(self, external_id: str) -> RemoteRun:
        """DELETE /sessions/{id} termine la session (seule forme d'annulation documentée)."""
        session_id = self._session_id(external_id)
        org = await self._org()
        await self._request("DELETE", self._org_path(org, f"/sessions/{session_id}"))
        # Devin n'a pas d'état « cancelled » : la suppression acceptée EST l'annulation.
        return RemoteRun(status=RemoteStatus.CANCELLED, external_id=external_id,
                         external_url=WEB_SESSION_URL + session_id)

    async def send_input(self, external_id: str, message: str) -> None:
        """POST /sessions/{id}/messages : message à une session active, relancée si suspendue (ADR-0010)."""
        session_id = self._session_id(external_id)
        org = await self._org()
        await self._request(
            "POST",
            self._org_path(org, f"/sessions/{session_id}/messages"),
            json={"message": message},
        )

    # ── mapping ──

    @staticmethod
    def _to_remote(session: dict[str, Any], *, fallback_id: str) -> RemoteRun:
        status = _STATUS.get(str(session.get("status", "")), RemoteStatus.PENDING)
        detail = str(session.get("status_detail") or "")
        if status == RemoteStatus.RUNNING and detail in _WAITING_DETAILS:
            status = RemoteStatus.WAITING
        elif status == RemoteStatus.PENDING and detail in _WAITING_DETAILS:
            status = RemoteStatus.WAITING

        pr_url = None
        for pr in session.get("pull_requests") or []:
            if isinstance(pr, dict) and pr.get("pr_url"):
                pr_url = pr["pr_url"]
                break

        session_id = session.get("session_id") or fallback_id
        error = None
        if status == RemoteStatus.WAITING:
            error = "Devin attend votre réponse ou votre approbation."
        elif status == RemoteStatus.FAILED:
            error = "La session a échoué chez Devin."
        return RemoteRun(
            status=status,
            external_id=session_id,
            external_url=WEB_SESSION_URL + session_id,
            summary=None,  # le résumé vit dans les messages de session, non exposé par GET /sessions/{id}
            branch=None,
            pr_url=pr_url,
            error_message=error,
        )
