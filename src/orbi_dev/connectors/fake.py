"""
Orbi Dev — Fournisseur factice « sandbox » (développement et tests uniquement).

Simule le cycle d'un agent distant en mémoire. Il n'est jamais disponible en production
(voir registry.py) et ne remplace PAS un essai réel contre un fournisseur (gate de la phase 3).

Le comportement se pilote avec des marqueurs dans le prompt :
  [fail]     l'exécution échoue au 2e suivi
  [auth]     le lancement est refusé (clé invalide)
  [lost]     le lancement réussit côté fournisseur mais la réponse est perdue (timeout)
  [slow]     l'exécution ne se termine jamais
  [ask]      l'agent pose une question et attend une réponse (remote control) jusqu'à send_input
"""

from datetime import UTC, datetime

from src.orbi_dev.connectors.base import (
    BaseConnector,
    Capability,
    ConnectorError,
    ErrorCategory,
    LaunchRequest,
    RemoteMessage,
    RemoteRun,
    RemoteStatus,
    VerifyResult,
)


class FakeConnector(BaseConnector):
    provider = "fake"
    capabilities = frozenset(
        {
            Capability.LAUNCH, Capability.STATUS, Capability.CANCEL,
            Capability.PULL_REQUEST, Capability.INTERACT, Capability.HISTORY,
        }
    )

    # État « côté fournisseur », partagé dans le process.
    _runs: dict[str, dict] = {}

    def __init__(self, api_key: str, **_: object):
        self._key = api_key

    @classmethod
    def reset(cls) -> None:
        cls._runs = {}

    def external_id_for(self, client_ref: str) -> str | None:
        return f"fake-{client_ref}"

    async def verify(self) -> VerifyResult:
        if self._key == "invalid":
            raise ConnectorError(ErrorCategory.AUTH_INVALID, "Clé invalide")
        return VerifyResult(capabilities=self.capabilities)

    async def launch(self, request: LaunchRequest) -> RemoteRun:
        if "[auth]" in request.prompt:
            raise ConnectorError(ErrorCategory.AUTH_INVALID, "Clé refusée par le fournisseur factice")
        external_id = self.external_id_for(request.client_ref)
        if external_id not in self._runs:  # idempotent : un doublon adopte l'existant
            self._runs[external_id] = {
                "polls": 0, "cancelled": False, "prompt": request.prompt, "repo": request.repo_url,
                "thread": [self._msg("user", request.prompt)],
            }
        if "[lost]" in request.prompt and self._runs[external_id]["polls"] == 0 and not self._runs[external_id].get("lost"):
            self._runs[external_id]["lost"] = True
            raise ConnectorError(ErrorCategory.TIMEOUT, "Réponse perdue", outcome_unknown=True)
        return self._snapshot(external_id)

    async def get(self, external_id: str) -> RemoteRun:
        run = self._runs.get(external_id)
        if run is None:
            raise ConnectorError(ErrorCategory.NOT_FOUND, "Agent introuvable")
        run["polls"] += 1
        return self._snapshot(external_id)

    async def send_input(self, external_id: str, message: str) -> None:
        run = self._runs.get(external_id)
        if run is None:
            raise ConnectorError(ErrorCategory.NOT_FOUND, "Agent introuvable")
        run.setdefault("messages", []).append(message)
        run.setdefault("thread", []).extend(
            [self._msg("user", message), self._msg("agent", "Message reçu, je continue.")]
        )
        run["answered"] = True

    async def list_messages(self, external_id: str, *, limit: int = 50) -> list[RemoteMessage]:
        run = self._runs.get(external_id)
        if run is None:
            raise ConnectorError(ErrorCategory.NOT_FOUND, "Agent introuvable")
        thread = list(run.get("thread") or [])
        if "[ask]" in run["prompt"] and not run.get("answered"):
            thread.append(self._msg("agent", "Question de l'agent : puis-je continuer ?"))
        return thread[-limit:]

    @staticmethod
    def _msg(role: str, text: str) -> RemoteMessage:
        return RemoteMessage(role=role, text=text, at=datetime.now(UTC))

    async def cancel(self, external_id: str) -> RemoteRun:
        run = self._runs.get(external_id)
        if run is None:
            raise ConnectorError(ErrorCategory.NOT_FOUND, "Agent introuvable")
        if self._snapshot(external_id).status in (RemoteStatus.SUCCEEDED, RemoteStatus.FAILED, RemoteStatus.CANCELLED):
            raise ConnectorError(ErrorCategory.CONFLICT, "Exécution déjà terminée", code="run_not_cancellable")
        run["cancelled"] = True
        return self._snapshot(external_id)

    def _snapshot(self, external_id: str) -> RemoteRun:
        run = self._runs[external_id]
        url = f"https://sandbox.invalid/agents/{external_id}"
        if run["cancelled"]:
            return RemoteRun(RemoteStatus.CANCELLED, external_id, url)
        polls, prompt = run["polls"], run["prompt"]
        if "[slow]" in prompt or polls < 2:
            return RemoteRun(RemoteStatus.PENDING if polls == 0 else RemoteStatus.RUNNING, external_id, url)
        if "[ask]" in prompt and not run.get("answered"):
            return RemoteRun(
                RemoteStatus.WAITING, external_id, url, error_message="L'agent attend une réponse."
            )
        if "[fail]" in prompt:
            return RemoteRun(RemoteStatus.FAILED, external_id, url, error_message="Échec simulé de l'agent")
        repo = run["repo"].removeprefix("https://github.com/")
        return RemoteRun(
            RemoteStatus.SUCCEEDED, external_id, url,
            summary="Modification simulée terminée.", branch="sandbox/orbi-change",
            pr_url=f"https://github.com/{repo}/pull/1",
        )
