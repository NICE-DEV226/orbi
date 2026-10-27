"""
Orbi Dev — Socle HTTP commun aux connecteurs : retries bornés, délais, erreurs réseau normalisées.

Chaque fournisseur ne fournit que ce qui le distingue : l'URL, les en-têtes d'authentification et la traduction d'une
réponse d'erreur en `ConnectorError` (`_error_from_response`).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from src.orbi_dev.connectors.base import BaseConnector, ConnectorError, ErrorCategory

logger = logging.getLogger("orbi.dev.http")

MAX_RETRY_AFTER = 30.0

# Erreurs réseau où la requête n'a certainement pas atteint le fournisseur.
NOT_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


def parse_retry_after(value: str | None) -> float | None:
    try:
        return min(max(float(value), 0.0), MAX_RETRY_AFTER) if value else None
    except ValueError:
        return None


class HttpConnector(BaseConnector):
    display_name: str = ""

    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str],
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 15.0,
        max_retries: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._client = httpx.AsyncClient(
            base_url=base_url, headers={"Accept": "application/json", **headers}, timeout=timeout, transport=transport
        )
        self._max_retries = max_retries
        self._sleep = sleep

    async def aclose(self) -> None:
        await self._client.aclose()

    def _error_from_response(self, response: httpx.Response) -> ConnectorError:
        raise NotImplementedError

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
                    ErrorCategory.TIMEOUT, f"Délai dépassé en contactant {self.display_name}",
                    retryable=isinstance(e, NOT_SENT), outcome_unknown=not isinstance(e, NOT_SENT),
                )
            except httpx.TransportError as e:
                error = ConnectorError(
                    ErrorCategory.UNAVAILABLE, f"{self.display_name} injoignable",
                    retryable=isinstance(e, NOT_SENT), outcome_unknown=not isinstance(e, NOT_SENT),
                )
            else:
                if response.is_success:
                    return response.json() if response.content else {}
                error = self._error_from_response(response)

            may_retry = error.retryable or (error.outcome_unknown and retry_unknown)
            if not may_retry or attempt >= self._max_retries:
                raise error
            attempt += 1
            delay = error.retry_after if error.retry_after is not None else min(0.5 * 2**attempt, 4.0)
            logger.info(
                "%s %s %s : nouvel essai %d/%d (%s)", self.display_name, method, path, attempt, self._max_retries,
                error.category,
            )
            await self._sleep(delay)
