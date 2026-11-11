"""Remote control (ADR-0010) : capacité INTERACT, send_input, réponse à l'agent depuis Orbi."""

import pytest
from cryptography.fernet import Fernet

from src.core.config import get_settings
from src.orbi_dev import runner, service
from src.orbi_dev.connectors.base import (
    BaseConnector,
    Capability,
    ConnectorError,
    ErrorCategory,
    LaunchRequest,
)
from src.orbi_dev.connectors.fake import FakeConnector
from src.orbi_dev.models import EventKind
from src.orbi_dev.state import ExecutionStatus as S

ALICE, BOB = 1001, 2002
SECRET = "key_super_secret_value_123456"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    FakeConnector.reset()
    yield
    FakeConnector.reset()


async def make_execution(prompt="Corrige le bug [ask]", owner=ALICE):
    project = await service.create_project(owner, "demo", "https://github.com/acme/demo")
    integration = await runner.connect_integration(owner, "fake", SECRET)
    task = await service.create_task(owner, str(project.id), str(integration.id), prompt)
    execution = await service.create_execution(owner, str(task.id))
    return integration, task, execution


async def waiting_execution(owner=ALICE):
    """Une exécution dont l'agent pose une question : NEEDS_ATTENTION côté Orbi."""
    _, _, execution = await make_execution(owner=owner)
    await runner.launch_execution(owner, str(execution.id))
    await runner.refresh_execution(owner, str(execution.id))  # RUNNING
    waiting = await runner.refresh_execution(owner, str(execution.id))  # WAITING -> NEEDS_ATTENTION
    assert waiting.status == S.NEEDS_ATTENTION
    return waiting


class TestContract:
    async def test_send_input_is_unsupported_by_default(self):
        connector = BaseConnector()
        with pytest.raises(ConnectorError) as exc:
            await connector.send_input("ext-1", "bonjour")
        assert exc.value.category == ErrorCategory.UNSUPPORTED_CAPABILITY

    async def test_fake_connector_declares_interact(self):
        result = await FakeConnector(SECRET).verify()
        assert Capability.INTERACT in result.capabilities


class TestSendInput:
    async def test_message_reaches_the_agent_and_the_run_resumes(self):
        execution = await waiting_execution()
        sent = await runner.send_input_to_execution(ALICE, str(execution.id), "Utilise Python 3.12")

        assert sent.status == S.RUNNING  # needs_attention -> running de façon optimiste
        run = FakeConnector._runs[execution.external_id]
        assert run["messages"] == ["Utilise Python 3.12"]

        kinds = [e.kind for e in await service.list_events(ALICE, str(execution.id))]
        assert EventKind.NOTE in kinds
        notes = [e.message for e in await service.list_events(ALICE, str(execution.id)) if e.kind == EventKind.NOTE]
        assert any("Utilise Python 3.12" in m for m in notes)

        done = await runner.refresh_execution(ALICE, str(execution.id))
        assert done.status == S.SUCCEEDED  # l'agent a repris et terminé

    async def test_reply_while_running_is_allowed(self):
        _, _, execution = await make_execution(prompt="Travail long [slow]")
        await runner.launch_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))
        execution = await service.get_execution(ALICE, str(execution.id))
        sent = await runner.send_input_to_execution(ALICE, str(execution.id), "pense à ajouter un test")
        assert sent.status == S.RUNNING
        assert FakeConnector._runs[execution.external_id]["messages"] == ["pense à ajouter un test"]

    async def test_empty_and_too_long_messages_are_refused(self):
        execution = await waiting_execution()
        with pytest.raises(ValueError):
            await runner.send_input_to_execution(ALICE, str(execution.id), "   ")
        with pytest.raises(ValueError):
            await runner.send_input_to_execution(ALICE, str(execution.id), "x" * 4001)
        assert "messages" not in FakeConnector._runs.get(execution.external_id, {})

    async def test_terminal_execution_refuses_messages(self):
        _, _, execution = await make_execution(prompt="ok")
        await runner.launch_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))
        assert (await service.get_execution(ALICE, str(execution.id))).status == S.SUCCEEDED
        with pytest.raises(service.ConflictError):
            await runner.send_input_to_execution(ALICE, str(execution.id), "encore")

    async def test_queued_execution_has_nobody_to_answer(self):
        _, _, execution = await make_execution()
        with pytest.raises(service.ConflictError):
            await runner.send_input_to_execution(ALICE, str(execution.id), "trop tôt")

    async def test_other_owner_cannot_message(self):
        execution = await waiting_execution()
        with pytest.raises(service.NotFoundError):
            await runner.send_input_to_execution(BOB, str(execution.id), "intrusion")
        assert "messages" not in FakeConnector._runs[execution.external_id]


class _NoInteractConnector:
    """Connecteur factice sans INTERACT : vérifie que le runner refuse explicitement."""

    provider = "fake"
    capabilities = frozenset({Capability.LAUNCH, Capability.STATUS})

    def __init__(self, secret: str):
        self.secret = secret

    async def aclose(self) -> None:
        return None

    async def send_input(self, external_id: str, message: str) -> None:  # pragma: no cover - ne doit pas être appelé
        raise AssertionError("send_input ne devrait pas être appelé sans la capacité")


class TestUnsupportedProvider:
    async def test_provider_without_interact_is_refused_and_journaled(self, monkeypatch):
        execution = await waiting_execution()
        monkeypatch.setattr(runner, "build_connector", lambda provider, secret: _NoInteractConnector(secret))

        with pytest.raises(ConnectorError) as exc:
            await runner.send_input_to_execution(ALICE, str(execution.id), "réponse")

        assert exc.value.category == ErrorCategory.UNSUPPORTED_CAPABILITY
        assert "messages" not in FakeConnector._runs[execution.external_id]
        errors = [
            e for e in await service.list_events(ALICE, str(execution.id)) if e.kind == EventKind.ERROR
        ]
        assert errors and "unsupported_capability" in errors[-1].message


class TestFakeConnectorInteract:
    async def test_send_input_records_the_message(self):
        connector = FakeConnector(SECRET)
        await connector.launch(LaunchRequest("ref-1", "fais [ask]", "https://github.com/acme/demo", "main"))
        await connector.send_input("fake-ref-1", "voici la réponse")
        assert connector._runs["fake-ref-1"]["messages"] == ["voici la réponse"]
        assert connector._runs["fake-ref-1"]["answered"] is True

    async def test_send_input_on_unknown_run_is_not_found(self):
        with pytest.raises(ConnectorError) as exc:
            await FakeConnector(SECRET).send_input("fake-nope", "salut")
        assert exc.value.category == ErrorCategory.NOT_FOUND


class TestExecutionThread:
    """runner.get_execution_thread : le fil de discussion (capacité HISTORY)."""

    async def test_thread_returns_the_provider_conversation(self):
        execution = await waiting_execution()
        await runner.send_input_to_execution(ALICE, str(execution.id), "Utilise Python 3.12")

        messages = await runner.get_execution_thread(ALICE, str(execution.id))

        roles = [m.role for m in messages]
        assert "user" in roles and "agent" in roles
        assert any("Utilise Python 3.12" in m.text for m in messages)
        assert any(m.role == "agent" and "Question de l'agent" in m.text for m in messages) is False

    async def test_waiting_agent_question_is_in_the_thread(self):
        execution = await waiting_execution()
        messages = await runner.get_execution_thread(ALICE, str(execution.id))
        assert any(m.role == "agent" and "Question de l'agent" in m.text for m in messages)

    async def test_thread_works_on_a_finished_execution(self):
        _, _, execution = await make_execution(prompt="ok")
        await runner.launch_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))
        assert (await service.get_execution(ALICE, str(execution.id))).status == S.SUCCEEDED

        messages = await runner.get_execution_thread(ALICE, str(execution.id))
        assert messages and messages[0].role == "user"

    async def test_queued_execution_has_no_thread_yet(self):
        _, _, execution = await make_execution()
        with pytest.raises(service.ConflictError):
            await runner.get_execution_thread(ALICE, str(execution.id))

    async def test_other_owner_cannot_read_the_thread(self):
        execution = await waiting_execution()
        with pytest.raises(service.NotFoundError):
            await runner.get_execution_thread(BOB, str(execution.id))


class _NoHistoryConnector(_NoInteractConnector):
    """Connecteur factice sans HISTORY : le runner doit refuser le fil explicitement."""

    capabilities = frozenset({Capability.LAUNCH, Capability.STATUS, Capability.INTERACT})

    async def list_messages(self, external_id: str, *, limit: int = 50):  # pragma: no cover
        raise AssertionError("list_messages ne devrait pas être appelé sans la capacité")


class TestThreadUnsupportedProvider:
    async def test_provider_without_history_is_refused(self, monkeypatch):
        execution = await waiting_execution()
        monkeypatch.setattr(runner, "build_connector", lambda provider, secret: _NoHistoryConnector(secret))

        with pytest.raises(ConnectorError) as exc:
            await runner.get_execution_thread(ALICE, str(execution.id))

        assert exc.value.category == ErrorCategory.UNSUPPORTED_CAPABILITY
