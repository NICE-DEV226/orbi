"""Tests de l'orchestration : lancement idempotent, réconciliation, suivi, annulation, révocation."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet

from src.core.config import get_settings
from src.orbi_dev import runner, service, worker
from src.orbi_dev.connectors.base import Capability, ConnectorError, ErrorCategory
from src.orbi_dev.connectors.fake import FakeConnector
from src.orbi_dev.models import EventKind, Execution, IntegrationStatus, TaskStatus
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


async def no_sleep(_: float) -> None:
    return None


async def make_execution(prompt="Corrige le bug", owner=ALICE, *, secret=SECRET):
    project = await service.create_project(owner, "demo", "https://github.com/acme/demo")
    integration = await runner.connect_integration(owner, "fake", secret)
    task = await service.create_task(owner, str(project.id), str(integration.id), prompt)
    execution = await service.create_execution(owner, str(task.id))
    return integration, task, execution


async def status_of(execution, owner=ALICE):
    return (await service.get_execution(owner, str(execution.id))).status


class TestConnect:
    async def test_invalid_key_is_rejected_and_nothing_is_stored(self):
        with pytest.raises(ConnectorError) as exc:
            await runner.connect_integration(ALICE, "fake", "invalid")
        assert exc.value.category == ErrorCategory.AUTH_INVALID
        assert await service.list_integrations(ALICE) == []

    async def test_valid_key_stores_capabilities_and_encrypted_secret(self):
        integration = await runner.connect_integration(ALICE, "fake", SECRET)
        assert set(integration.capabilities) >= {"launch", "status", "cancel"}
        ciphertext = await service.get_secret_ciphertext(ALICE, str(integration.id))
        assert ciphertext and SECRET not in ciphertext


class TestLaunchAndFollow:
    async def test_happy_path_to_pull_request(self):
        _, task, execution = await make_execution()

        launched = await runner.launch_execution(ALICE, str(execution.id))
        assert launched.status == S.RUNNING
        assert launched.external_id == f"fake-{execution.client_ref}"

        await runner.refresh_execution(ALICE, str(execution.id))  # RUNNING
        done = await runner.refresh_execution(ALICE, str(execution.id))  # SUCCEEDED

        assert done.status == S.SUCCEEDED
        assert done.pr_url == "https://github.com/acme/demo/pull/1"
        assert done.branch == "sandbox/orbi-change"
        assert done.finished_at is not None
        assert (await service.get_task(ALICE, str(task.id))).status == TaskStatus.COMPLETED

    async def test_events_tell_the_story(self):
        _, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))

        events = await service.list_events(ALICE, str(execution.id))

        assert [e.seq for e in events] == list(range(1, len(events) + 1))
        assert [e.to_status for e in events if e.kind == EventKind.STATUS_CHANGED] == [S.RUNNING, S.SUCCEEDED]

    async def test_launching_twice_does_not_create_a_second_remote_run(self):
        _, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))

        with pytest.raises(service.ConflictError):
            await runner.launch_execution(ALICE, str(execution.id))

        assert len(FakeConnector._runs) == 1

    async def test_crash_after_remote_creation_adopts_the_existing_run(self):
        """Le process s'arrête après l'appel réseau mais avant la transition : le rappel ne duplique rien."""
        _, _, execution = await make_execution()
        FakeConnector._runs[f"fake-{execution.client_ref}"] = {
            "polls": 0, "cancelled": False, "prompt": "Corrige le bug", "repo": "https://github.com/acme/demo",
        }

        launched = await runner.launch_execution(ALICE, str(execution.id))

        assert launched.status == S.RUNNING
        assert len(FakeConnector._runs) == 1

    async def test_lost_response_is_reconciled_without_second_launch(self):
        _, _, execution = await make_execution("tâche [lost]")

        launched = await runner.launch_execution(ALICE, str(execution.id))

        assert launched.status == S.RUNNING
        assert len(FakeConnector._runs) == 1
        kinds = [e.kind for e in await service.list_events(ALICE, str(execution.id))]
        assert EventKind.RECONCILIATION in kinds

    async def test_unreconcilable_lost_response_needs_attention_then_recovers(self, monkeypatch):
        _, _, execution = await make_execution("tâche [lost]")
        real_get = FakeConnector.get

        async def failing_get(self, external_id):
            raise ConnectorError(ErrorCategory.TIMEOUT, "toujours muet", outcome_unknown=True)

        monkeypatch.setattr(FakeConnector, "get", failing_get)
        stuck = await runner.launch_execution(ALICE, str(execution.id))
        assert stuck.status == S.NEEDS_ATTENTION
        assert stuck.error_category == ErrorCategory.TIMEOUT.value
        assert len(FakeConnector._runs) == 1  # aucun relancement à l'aveugle

        monkeypatch.setattr(FakeConnector, "get", real_get)
        recovered = await runner.refresh_execution(ALICE, str(execution.id))
        assert recovered.status == S.RUNNING

    async def test_rate_limited_launch_is_retried_with_bounded_backoff(self, monkeypatch):
        _, _, execution = await make_execution()
        real_launch = FakeConnector.launch
        calls = []

        async def flaky(self, request):
            calls.append(1)
            if len(calls) < 3:
                raise ConnectorError(ErrorCategory.RATE_LIMITED, "slow", retryable=True, retry_after=4)
            return await real_launch(self, request)

        monkeypatch.setattr(FakeConnector, "launch", flaky)
        slept = []

        async def record_sleep(seconds):
            slept.append(seconds)

        launched = await runner.launch_execution(ALICE, str(execution.id), sleep=record_sleep)

        assert launched.status == S.RUNNING
        assert len(calls) == 3
        assert slept == [4, 4]

    async def test_retries_are_bounded(self, monkeypatch):
        _, _, execution = await make_execution()
        calls = []

        async def always_down(self, request):
            calls.append(1)
            raise ConnectorError(ErrorCategory.UNAVAILABLE, "down", retryable=True)

        monkeypatch.setattr(FakeConnector, "launch", always_down)

        failed = await runner.launch_execution(ALICE, str(execution.id), sleep=no_sleep)

        assert len(calls) == runner.MAX_LAUNCH_ATTEMPTS
        assert failed.status == S.FAILED
        assert failed.error_category == ErrorCategory.UNAVAILABLE.value

    async def test_invalid_credentials_fail_the_execution_and_flag_the_integration(self):
        integration, _, execution = await make_execution("tâche [auth]")

        failed = await runner.launch_execution(ALICE, str(execution.id))

        assert failed.status == S.FAILED
        assert failed.error_category == ErrorCategory.AUTH_INVALID.value
        assert (await service.get_integration(ALICE, str(integration.id))).status == IntegrationStatus.INVALID

    async def test_agent_failure_is_reported(self):
        _, _, execution = await make_execution("tâche [fail]")
        await runner.launch_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))

        failed = await runner.refresh_execution(ALICE, str(execution.id))

        assert failed.status == S.FAILED
        assert "Échec simulé" in failed.error_message

    async def test_transient_poll_error_keeps_state(self, monkeypatch):
        _, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))

        async def down(self, external_id):
            raise ConnectorError(ErrorCategory.UNAVAILABLE, "down", retryable=True)

        monkeypatch.setattr(FakeConnector, "get", down)

        result = await runner.refresh_execution(ALICE, str(execution.id))

        assert result.status == S.RUNNING

    async def test_remote_disappearance_needs_attention(self):
        _, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        FakeConnector.reset()

        result = await runner.refresh_execution(ALICE, str(execution.id))

        assert result.status == S.NEEDS_ATTENTION

    async def test_state_survives_a_restart(self):
        """Aucun état en mémoire : une relecture complète depuis la base reproduit la situation."""
        _, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))

        reloaded = await Execution.get(execution.id)

        assert reloaded.status == S.RUNNING
        assert reloaded.external_id


class TestDeadline:
    async def test_expired_execution_is_cancelled_remotely_and_timed_out(self):
        _, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        await service.set_execution_fields(execution)
        await Execution.get_pymongo_collection().update_one(
            {"_id": execution.id}, {"$set": {"deadline_at": datetime.now(UTC) - timedelta(minutes=1)}}
        )

        result = await runner.refresh_execution(ALICE, str(execution.id))

        assert result.status == S.TIMED_OUT
        assert FakeConnector._runs[f"fake-{execution.client_ref}"]["cancelled"] is True


class TestCancel:
    async def test_cancel_before_launch_never_calls_the_provider(self):
        _, _, execution = await make_execution()

        result = await runner.request_cancel(ALICE, str(execution.id))

        assert result.status == S.CANCELLED
        assert FakeConnector._runs == {}

    async def test_cancel_running_execution(self):
        _, task, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))

        result = await runner.request_cancel(ALICE, str(execution.id))

        assert result.status == S.CANCELLED
        assert (await service.get_task(ALICE, str(task.id))).status == TaskStatus.CANCELLED

    async def test_cancel_unsupported_is_explicit_and_changes_nothing(self, monkeypatch):
        _, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        monkeypatch.setattr(FakeConnector, "capabilities", frozenset({Capability.LAUNCH, Capability.STATUS}))

        with pytest.raises(ConnectorError) as exc:
            await runner.request_cancel(ALICE, str(execution.id))

        assert exc.value.category == ErrorCategory.UNSUPPORTED_CAPABILITY
        assert await status_of(execution) == S.RUNNING

    async def test_cancel_finished_execution_is_refused(self):
        _, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))

        with pytest.raises(service.ConflictError):
            await runner.request_cancel(ALICE, str(execution.id))

    async def test_cancel_that_loses_the_race_resolves_to_the_real_outcome(self, monkeypatch):
        _, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))
        # Le fournisseur a déjà terminé : l'annulation reçoit « run_not_cancellable ».
        FakeConnector._runs[f"fake-{execution.client_ref}"]["polls"] = 5

        async def too_late(self, external_id):
            raise ConnectorError(ErrorCategory.CONFLICT, "done", code="run_not_cancellable")

        monkeypatch.setattr(FakeConnector, "cancel", too_late)

        result = await runner.request_cancel(ALICE, str(execution.id))

        assert result.status == S.SUCCEEDED


class TestRevocation:
    async def test_revoke_erases_secret_and_flags_active_executions(self):
        integration, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))

        await runner.revoke_integration(ALICE, str(integration.id))

        assert await status_of(execution) == S.NEEDS_ATTENTION
        refreshed = await service.get_integration(ALICE, str(integration.id))
        assert await service.get_secret_ciphertext(ALICE, str(integration.id)) is None
        assert refreshed.status == IntegrationStatus.REVOKED
        # le suivi ne plante pas et ne contacte plus le fournisseur
        assert (await runner.refresh_execution(ALICE, str(execution.id))).status == S.NEEDS_ATTENTION

    async def test_revoked_integration_cannot_launch(self):
        integration, _, execution = await make_execution()

        await runner.revoke_integration(ALICE, str(integration.id))

        assert await status_of(execution) == S.NEEDS_ATTENTION
        with pytest.raises(service.ConflictError):
            await runner.launch_execution(ALICE, str(execution.id))
        assert FakeConnector._runs == {}


class TestWorker:
    async def test_refresh_active_executions_follows_and_relaunches_stuck(self):
        _, _, running = await make_execution()
        await runner.launch_execution(ALICE, str(running.id))
        _, _, stuck = await make_execution()
        await Execution.get_pymongo_collection().update_one(
            {"_id": stuck.id}, {"$set": {"updated_at": datetime.now(UTC) - timedelta(minutes=5)}}
        )

        processed = await runner.refresh_active_executions()

        assert processed >= 2
        assert await status_of(stuck) == S.RUNNING

    async def test_one_failing_execution_does_not_block_the_others(self, monkeypatch):
        _, _, a = await make_execution()
        await runner.launch_execution(ALICE, str(a.id))
        _, _, b = await make_execution()
        await runner.launch_execution(ALICE, str(b.id))
        original = runner.refresh_execution
        seen = []

        async def flaky(owner_id, execution_id):
            seen.append(execution_id)
            if len(seen) == 1:
                raise RuntimeError("boom")
            return await original(owner_id, execution_id)

        monkeypatch.setattr(runner, "refresh_execution", flaky)

        assert await runner.refresh_active_executions() == 1
        assert len(seen) == 2

    async def test_lock_prevents_concurrent_passes(self):
        first = await worker.run_once()
        second = await worker.run_once()

        assert first is not None
        assert second is None

    async def test_concurrent_refreshes_converge_without_error(self):
        _, _, execution = await make_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        await runner.refresh_execution(ALICE, str(execution.id))
        FakeConnector._runs[f"fake-{execution.client_ref}"]["polls"] = 5

        results = await asyncio.gather(*[runner.refresh_execution(ALICE, str(execution.id)) for _ in range(4)])

        assert {r.status for r in results} == {S.SUCCEEDED}
        events = await service.list_events(ALICE, str(execution.id))
        assert sum(1 for e in events if e.to_status == S.SUCCEEDED) == 1


class TestIsolation:
    async def test_other_user_cannot_drive_an_execution(self):
        _, _, execution = await make_execution(owner=ALICE)

        for call in (runner.launch_execution, runner.refresh_execution, runner.request_cancel):
            with pytest.raises(service.NotFoundError):
                await call(BOB, str(execution.id))

    async def test_other_user_cannot_revoke_an_integration(self):
        integration, _, _ = await make_execution(owner=ALICE)
        with pytest.raises(service.NotFoundError):
            await runner.revoke_integration(BOB, str(integration.id))


class TestNoSecretLeak:
    async def test_secret_absent_from_every_persisted_document(self):
        _, _, execution = await make_execution("tâche [auth]")
        await runner.launch_execution(ALICE, str(execution.id))

        from src.core.database import get_database

        db = get_database()
        for name in await db.list_collection_names():
            async for doc in db[name].find({}):
                assert SECRET not in str(doc), name
