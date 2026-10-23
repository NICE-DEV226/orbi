"""
Orbi Dev — Connecteur Cursor Cloud Agents API v1 (ADR-0004).

Écrit d'après la documentation et la spécification OpenAPI officielles
(https://cursor.com/docs/cloud-agent/api/overview). API en bêta publique : voir docs/connectors/cursor.md
pour les hypothèses et ce qui n'a pas été vérifié contre un compte réel.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from src.orbi_dev.connectors.base import (
    BaseConnector,
    Capability,
    ConnectorError,
    ErrorCategory,
    LaunchRequest,
    RemoteRun,
    RemoteStatus,
    VerifyResult,
)
from src.orbi_dev.redact import sanitize_text

logger = logging.getLogger("orbi.dev.cursor")

DEFAULT_BASE_URL = "https://api.cursor.com"
MAX_RETRY_AFTER = 30.0

_RUN_STATUS = {
    "CREATING": RemoteStatus.PENDING,
    "RUNNING": RemoteStatus.RUNNING,
    "FINISHED": RemoteStatus.SUCCEEDED,
    "ERROR": RemoteStatus.FAILED,
    "CANCELLED": RemoteStatus.CANCELLED,
    "EXPIRED": RemoteStatus.EXPIRED,
}

_CODE_CATEGORY = {
    "unauthorized": ErrorCategory.AUTH_INVALID,
    "api_key_not_found": ErrorCategory.AUTH_INVALID,
    "key_not_supported": ErrorCategory.AUTH_INVALID,
    "plan_required": ErrorCategory.PLAN_OR_QUOTA,
    "usage_limit_exceeded": ErrorCategory.PLAN_OR_QUOTA,
    "role_forbidden": ErrorCategory.PERMISSION_DENIED,
    "team_admin_required": ErrorCategory.PERMISSION_DENIED,
    "repository_access": ErrorCategory.PERMISSION_DENIED,
    "integration_not_connected": ErrorCategory.PERMISSION_DENIED,
    "rate_limit_exceeded": ErrorCategory.RATE_LIMITED,
    "agent_not_found": ErrorCategory.NOT_FOUND,
    "run_not_found": ErrorCategory.NOT_FOUND,
    "agent_busy": ErrorCategory.CONFLICT,
    "agent_id_conflict": ErrorCategory.CONFLICT,
    "agent_archived": ErrorCategory.CONFLICT,
    "run_not_cancellable": ErrorCategory.CONFLICT,
    "validation_error": ErrorCategory.INVALID_REQUEST,
    "invalid_model": ErrorCategory.INVALID_REQUEST,
    "invalid_branch_name": ErrorCategory.INVALID_REQUEST,
    "repository_required": ErrorCategory.INVALID_REQUEST,
    "upstream_error": ErrorCategory.UNAVAILABLE,
    "internal_error": ErrorCategory.UNAVAILABLE,
}

_STATUS_CATEGORY = {
    400: ErrorCategory.INVALID_REQUEST,
    401: ErrorCategory.AUTH_INVALID,
    403: ErrorCategory.PERMISSION_DENIED,
    404: ErrorCategory.NOT_FOUND,
    409: ErrorCategory.CONFLICT,
    429: ErrorCategory.RATE_LIMITED,
}

# Erreurs réseau où la requête n'a certainement pas atteint le fournisseur.
_NOT_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


def _parse_retry_after(value: str | None) -> float | None:
    try:
        return min(max(float(value), 0.0), MAX_RETRY_AFTER) if value else None
    except ValueError:
        return None


def error_from_response(response: httpx.Response) -> ConnectorError:
    """Traduit une réponse d'erreur en ConnectorError, sans jamais reprendre d'en-têtes ni de corps bruts."""
    code: str | None = None
    message = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error") if isinstance(body.get("error"), dict) else body
            code = error.get("code") if isinstance(error.get("code"), str) else None
            message = error.get("message") if isinstance(error.get("message"), str) else ""
    except ValueError:
        pass

    status = response.status_code
    category = _CODE_CATEGORY.get(code or "") or _STATUS_CATEGORY.get(status)
    if category is None:
        category = ErrorCategory.UNAVAILABLE if status >= 500 else ErrorCategory.UNKNOWN
    retry_after = _parse_retry_after(response.headers.get("retry-after"))
    retryable = category in (ErrorCategory.RATE_LIMITED, ErrorCategory.UNAVAILABLE)
    return ConnectorError(
        category,
        sanitize_text(message, 300) or f"Erreur du fournisseur (HTTP {status})",
        code=code,
        retryable=retryable,
        retry_after=retry_after,
    )


class CursorCloudAgentsConnector(BaseConnector):
    provider = "cursor"
    capabilities = frozenset({Capability.LAUNCH, Capability.STATUS, Capability.CANCEL, Capability.PULL_REQUEST})

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
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )
        self._max_retries = max_retries
        self._sleep = sleep

    async def aclose(self) -> None:
        await self._client.aclose()

    def external_id_for(self, client_ref: str) -> str | None:
        # Format imposé par l'API : bc-<uuid>. `client_ref` est un UUID généré par Orbi.
        return f"bc-{client_ref}"

    # ── transport ──

    async def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None,
        retry_unknown: bool = False,
    ) -> dict[str, Any]:
        """
        Envoie une requête avec retries bornés.

        On réessaie : les erreurs de limite/indisponibilité, et les erreurs réseau où l'envoi est
        exclu. Une réponse perdue après envoi n'est réessayée que si `retry_unknown` (opération idempotente).
        """
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, path, json=json, params=params)
            except httpx.TimeoutException as e:
                error = ConnectorError(
                    ErrorCategory.TIMEOUT, "Délai dépassé en contactant Cursor",
                    retryable=isinstance(e, _NOT_SENT), outcome_unknown=not isinstance(e, _NOT_SENT),
                )
            except httpx.TransportError as e:
                error = ConnectorError(
                    ErrorCategory.UNAVAILABLE, "Cursor injoignable",
                    retryable=isinstance(e, _NOT_SENT), outcome_unknown=not isinstance(e, _NOT_SENT),
                )
            else:
                if response.is_success:
                    return response.json() if response.content else {}
                error = error_from_response(response)

            may_retry = error.retryable or (error.outcome_unknown and retry_unknown)
            if not may_retry or attempt >= self._max_retries:
                raise error
            attempt += 1
            delay = error.retry_after if error.retry_after is not None else min(0.5 * 2**attempt, 4.0)
            logger.info("Cursor %s %s : nouvel essai %d/%d (%s)", method, path, attempt, self._max_retries, error.category)
            await self._sleep(delay)

    # ── contrat ──

    async def verify(self) -> VerifyResult:
        # Lecture seule : prouve que la clé est valide, sans créer de ressource ni consommer de quota d'agent.
        await self._request("GET", "/v1/agents", params={"limit": 1})
        return VerifyResult(capabilities=self.capabilities)

    async def launch(self, request: LaunchRequest) -> RemoteRun:
        agent_id = self.external_id_for(request.client_ref)
        body = {
            "agentId": agent_id,
            "prompt": {"text": request.prompt},
            "repos": [{"url": request.repo_url, "startingRef": request.base_branch}],
            "autoCreatePR": True,
        }
        try:
            # Idempotent grâce à `agentId` : on peut réessayer après un délai dépassé sans risque de doublon.
            data = await self._request("POST", "/v1/agents", json=body, retry_unknown=True)
        except ConnectorError as e:
            if e.code == "agent_id_conflict":
                return await self.get(agent_id)  # déjà créé (réponse précédente perdue) : on adopte
            raise
        return self._to_remote(data.get("agent", {}), data.get("run", {}), fallback_id=agent_id)

    async def get(self, external_id: str) -> RemoteRun:
        agent = await self._request("GET", f"/v1/agents/{external_id}")
        run: dict[str, Any] = {}
        run_id = agent.get("latestRunId")
        if run_id:
            run = await self._request("GET", f"/v1/agents/{external_id}/runs/{run_id}")
        return self._to_remote(agent, run, fallback_id=external_id)

    async def cancel(self, external_id: str) -> RemoteRun:
        agent = await self._request("GET", f"/v1/agents/{external_id}")
        run_id = agent.get("latestRunId")
        if not run_id:
            raise ConnectorError(ErrorCategory.CONFLICT, "Aucune exécution à annuler", code="run_not_cancellable")
        # Pas de retry sur résultat inconnu : l'appelant relit l'état via get().
        await self._request("POST", f"/v1/agents/{external_id}/runs/{run_id}/cancel")
        return await self.get(external_id)

    # ── mapping ──

    @staticmethod
    def _to_remote(agent: dict[str, Any], run: dict[str, Any], *, fallback_id: str) -> RemoteRun:
        status = _RUN_STATUS.get(str(run.get("status", "")), RemoteStatus.PENDING)
        if status in (RemoteStatus.PENDING, RemoteStatus.RUNNING) and agent.get("status") == "ARCHIVED":
            status = RemoteStatus.EXPIRED

        branch = pr_url = None
        branches = (run.get("git") or {}).get("branches") or []
        for item in branches:
            if not isinstance(item, dict):
                continue
            branch = branch or item.get("branch")
            if item.get("prUrl"):
                branch, pr_url = item.get("branch") or branch, item["prUrl"]
                break

        summary = run.get("result") if isinstance(run.get("result"), str) else None
        return RemoteRun(
            status=status,
            external_id=agent.get("id") or fallback_id,
            external_url=agent.get("url"),
            summary=summary,
            branch=branch,
            pr_url=pr_url,
            error_message=summary if status == RemoteStatus.FAILED else None,
        )


