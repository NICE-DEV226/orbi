"""Tests du modèle de domaine Orbi Dev : machine à états, isolation, secrets, événements."""

import itertools

import pytest
from cryptography.fernet import Fernet

from src.core.config import get_settings
from src.orbi_dev import service
from src.orbi_dev.crypto import (
    SecretDecryptionError,
    SecretsNotConfiguredError,
    decrypt_secret,
    encrypt_secret,
)
from src.orbi_dev.models import Execution, Integration, IntegrationSecret, IntegrationStatus, TaskStatus
from src.orbi_dev.state import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    ExecutionStatus,
    InvalidTransitionError,
    can_transition,
)

ALICE, BOB = 1001, 2002
SECRET = "key_super_secret_value_123456"


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()


async def _setup(owner=ALICE):
    project = await service.create_project(owner, "demo", "https://github.com/acme/demo")
    integration = await service.create_integration(owner, "fake", SECRET, capabilities=["launch"])
    task = await service.create_task(owner, str(project.id), str(integration.id), "Corrige le bug")
    return project, integration, task


class TestStateMachine:
    def test_terminal_states_allow_nothing(self):
        for status in TERMINAL_STATUSES:
            assert ALLOWED_TRANSITIONS[status] == frozenset()

    def test_every_status_is_described(self):
        assert set(ALLOWED_TRANSITIONS) == set(ExecutionStatus)

    @pytest.mark.parametrize("current,target", list(itertools.product(ExecutionStatus, ExecutionStatus)))
    def test_matrix_matches_table(self, current, target):
        assert can_transition(current, target) == (target in ALLOWED_TRANSITIONS[current])

    def test_no_blind_retry_from_needs_attention_to_queued(self):
        assert not can_transition(ExecutionStatus.NEEDS_ATTENTION, ExecutionStatus.QUEUED)

    def test_cancel_can_lose_the_race_against_success(self):
        assert can_transition(ExecutionStatus.CANCEL_REQUESTED, ExecutionStatus.SUCCEEDED)


class TestSecrets:
    def test_roundtrip(self):
        assert decrypt_secret(encrypt_secret(SECRET)) == SECRET

    def test_ciphertext_does_not_contain_secret(self):
        assert SECRET not in encrypt_secret(SECRET)

    def test_refuses_to_encrypt_without_key(self, monkeypatch):
        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "")
        get_settings.cache_clear()
        with pytest.raises(SecretsNotConfiguredError):
            encrypt_secret(SECRET)

    def test_invalid_key_is_rejected(self, monkeypatch):
        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "not-a-fernet-key")
        get_settings.cache_clear()
        with pytest.raises(SecretsNotConfiguredError):
            encrypt_secret(SECRET)

    def test_key_rotation_keeps_old_secrets_readable(self, monkeypatch):
        old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", old)
        get_settings.cache_clear()
        token = encrypt_secret(SECRET)

        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", f"{new},{old}")
        get_settings.cache_clear()

        assert decrypt_secret(token) == SECRET
        assert decrypt_secret(encrypt_secret(SECRET)) == SECRET

    def test_unreadable_secret_raises(self, monkeypatch):
        token = encrypt_secret(SECRET)
        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
        get_settings.cache_clear()
        with pytest.raises(SecretDecryptionError):
            decrypt_secret(token)

    async def test_secret_is_stored_encrypted_in_its_own_collection(self):
        _, integration, _ = await _setup()

        raw = await Integration.get_pymongo_collection().find_one({"_id": integration.id})
        assert "ciphertext" not in str(raw) and SECRET not in str(raw)
        stored = await IntegrationSecret.get_pymongo_collection().find_one({"integration_id": str(integration.id)})
        assert stored["ciphertext"] and SECRET not in str(stored)
        assert decrypt_secret(stored["ciphertext"]) == SECRET

    async def test_integration_model_cannot_leak_the_secret(self):
        _, integration, _ = await _setup()

        assert "ciphertext" not in integration.model_dump()
        assert "ciphertext" not in integration.model_dump_json()
        assert SECRET not in repr(integration)
        assert not hasattr(integration, "secret_ciphertext")

    async def test_revoke_erases_the_secret(self):
        _, integration, _ = await _setup()

        revoked = await service.revoke_integration(ALICE, str(integration.id))

        assert await IntegrationSecret.get_pymongo_collection().find_one({"integration_id": str(integration.id)}) is None
        assert await service.get_secret_ciphertext(ALICE, str(integration.id)) is None
        assert revoked.status == IntegrationStatus.REVOKED

    async def test_secret_is_only_readable_by_its_owner(self):
        _, integration, _ = await _setup(ALICE)
        assert await service.get_secret_ciphertext(BOB, str(integration.id)) is None

    async def test_no_active_integration_is_left_without_a_secret_when_storing_fails(self, monkeypatch):
        async def boom(self, *a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(IntegrationSecret, "insert", boom)
        with pytest.raises(RuntimeError):
            await service.create_integration(ALICE, "fake", SECRET)
        assert await service.list_integrations(ALICE) == []


class TestOwnershipIsolation:
    async def test_other_user_cannot_read_resources(self):
        project, integration, task = await _setup(ALICE)
        execution = await service.create_execution(ALICE, str(task.id))

        with pytest.raises(service.NotFoundError):
            await service.get_project(BOB, str(project.id))
        with pytest.raises(service.NotFoundError):
            await service.get_integration(BOB, str(integration.id))
        with pytest.raises(service.NotFoundError):
            await service.get_task(BOB, str(task.id))
        with pytest.raises(service.NotFoundError):
            await service.get_execution(BOB, str(execution.id))
        with pytest.raises(service.NotFoundError):
            await service.list_events(BOB, str(execution.id))

    async def test_listings_are_scoped(self):
        await _setup(ALICE)
        assert await service.list_projects(BOB) == []
        assert await service.list_tasks(BOB) == []
        assert await service.list_integrations(BOB) == []

    async def test_cannot_create_task_with_foreign_project_or_integration(self):
        project, integration, _ = await _setup(ALICE)
        with pytest.raises(service.NotFoundError):
            await service.create_task(BOB, str(project.id), str(integration.id), "x")

    async def test_other_user_cannot_transition_an_execution(self):
        _, _, task = await _setup(ALICE)
        execution = await service.create_execution(ALICE, str(task.id))
        with pytest.raises(service.NotFoundError):
            await service.transition_execution(
                BOB, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.RUNNING
            )

    async def test_malformed_id_is_not_found(self):
        with pytest.raises(service.NotFoundError):
            await service.get_project(ALICE, "not-an-object-id")


class TestProjectValidation:
    @pytest.mark.parametrize("url", ["http://github.com/a/b", "git@github.com:a/b.git", "file:///etc/passwd", "https://x y"])
    async def test_only_https_urls(self, url):
        with pytest.raises(ValueError):
            await service.create_project(ALICE, "p", url)


class TestExecutions:
    async def test_creation_assigns_durable_identifiers_before_any_call(self):
        _, _, task = await _setup()

        execution = await service.create_execution(ALICE, str(task.id))

        assert execution.status == ExecutionStatus.QUEUED
        assert execution.attempt == 1
        assert execution.client_ref and execution.idempotency_key
        assert execution.external_id is None
        assert execution.deadline_at is not None

    async def test_approval_required_starts_awaiting_approval(self):
        _, _, task = await _setup()
        execution = await service.create_execution(ALICE, str(task.id), requires_approval=True)
        assert execution.status == ExecutionStatus.AWAITING_APPROVAL

    async def test_no_second_execution_while_one_is_active(self):
        _, _, task = await _setup()
        await service.create_execution(ALICE, str(task.id))
        with pytest.raises(service.ConflictError):
            await service.create_execution(ALICE, str(task.id))

    async def test_new_attempt_after_terminal_gets_new_identifiers(self):
        _, _, task = await _setup()
        first = await service.create_execution(ALICE, str(task.id))
        await service.transition_execution(ALICE, str(first.id), ExecutionStatus.QUEUED, ExecutionStatus.FAILED)

        second = await service.create_execution(ALICE, str(task.id))

        assert second.attempt == 2
        assert second.idempotency_key != first.idempotency_key
        assert second.client_ref != first.client_ref

    def test_idempotency_key_is_stable(self):
        assert service.make_idempotency_key("t1", 1) == service.make_idempotency_key("t1", 1)
        assert service.make_idempotency_key("t1", 1) != service.make_idempotency_key("t1", 2)

    async def test_cannot_create_execution_with_revoked_integration(self):
        _, integration, task = await _setup()
        await service.revoke_integration(ALICE, str(integration.id))
        with pytest.raises(service.ConflictError):
            await service.create_execution(ALICE, str(task.id))


class TestTransitions:
    async def _execution(self):
        _, _, task = await _setup()
        return await service.create_execution(ALICE, str(task.id))

    async def test_valid_transition_updates_state_and_records_event(self):
        execution = await self._execution()

        updated = await service.transition_execution(
            ALICE, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, message="lancé",
            external_id="ext-1",
        )

        assert updated.status == ExecutionStatus.RUNNING
        assert updated.external_id == "ext-1"
        assert updated.version == 1
        events = await service.list_events(ALICE, str(execution.id))
        assert [e.seq for e in events] == [1, 2]
        assert events[-1].from_status == ExecutionStatus.QUEUED
        assert events[-1].to_status == ExecutionStatus.RUNNING

    async def test_illegal_transition_is_rejected(self):
        execution = await self._execution()
        with pytest.raises(InvalidTransitionError):
            await service.transition_execution(
                ALICE, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.SUCCEEDED
            )
        assert (await service.get_execution(ALICE, str(execution.id))).status == ExecutionStatus.QUEUED

    async def test_stale_expected_status_is_rejected_not_overwritten(self):
        execution = await self._execution()
        await service.transition_execution(ALICE, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.RUNNING)

        # Un second acteur croit encore que l'exécution est « queued ».
        with pytest.raises(InvalidTransitionError):
            await service.transition_execution(
                ALICE, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.FAILED
            )
        assert (await service.get_execution(ALICE, str(execution.id))).status == ExecutionStatus.RUNNING

    async def test_terminal_state_is_final(self):
        execution = await self._execution()
        await service.transition_execution(ALICE, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.FAILED)
        for target in ExecutionStatus:
            with pytest.raises(InvalidTransitionError):
                await service.transition_execution(ALICE, str(execution.id), ExecutionStatus.FAILED, target)

    async def test_terminal_transition_sets_finished_at(self):
        execution = await self._execution()
        done = await service.transition_execution(
            ALICE, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.FAILED
        )
        assert done.finished_at is not None

    async def test_success_completes_the_task(self):
        _, _, task = await _setup()
        execution = await service.create_execution(ALICE, str(task.id))
        await service.transition_execution(ALICE, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.RUNNING)
        await service.transition_execution(
            ALICE, str(execution.id), ExecutionStatus.RUNNING, ExecutionStatus.SUCCEEDED,
            pr_url="https://github.com/acme/demo/pull/1",
        )
        assert (await service.get_task(ALICE, str(task.id))).status == TaskStatus.COMPLETED

    async def test_unknown_field_is_refused(self):
        execution = await self._execution()
        with pytest.raises(ValueError):
            await service.transition_execution(
                ALICE, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, status="succeeded"
            )

    async def test_secrets_in_error_messages_are_redacted(self):
        execution = await self._execution()
        done = await service.transition_execution(
            ALICE, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.FAILED,
            error_message=f"401 Authorization: Bearer {SECRET} refused; api_key={SECRET}",
            message=f"token={SECRET}",
        )
        assert SECRET not in done.error_message
        events = await service.list_events(ALICE, str(execution.id))
        assert all(SECRET not in e.message for e in events)

    async def test_execution_is_persisted_across_reload(self):
        execution = await self._execution()
        await service.transition_execution(ALICE, str(execution.id), ExecutionStatus.QUEUED, ExecutionStatus.RUNNING)

        reloaded = await Execution.get(execution.id)

        assert reloaded.status == ExecutionStatus.RUNNING


class TestAudit:
    async def test_actions_are_audited_without_secret(self):
        from src.orbi_dev.models import AuditRecord

        await _setup()

        records = await AuditRecord.find().to_list()
        assert {r.action for r in records} >= {"project.create", "integration.connect", "task.create"}
        assert all(SECRET not in r.model_dump_json() for r in records)


class TestLegacySecretMigration:
    """Intégrations créées avant la migration : le secret était dans le document `Integration`."""

    async def _legacy_integration(self, status="active"):
        from src.orbi_dev.models import Integration

        integration = Integration(owner_id=ALICE, provider="fake", status=status)
        await integration.insert()
        await Integration.get_pymongo_collection().update_one(
            {"_id": integration.id}, {"$set": {"secret_ciphertext": encrypt_secret(SECRET)}}
        )
        return integration

    async def test_legacy_secret_is_moved_and_the_old_field_removed(self):
        from src.orbi_dev.migrations import migrate_legacy_secrets

        integration = await self._legacy_integration()

        assert await migrate_legacy_secrets() == 1

        raw = await Integration.get_pymongo_collection().find_one({"_id": integration.id})
        assert "secret_ciphertext" not in raw
        assert decrypt_secret(await service.get_secret_ciphertext(ALICE, str(integration.id))) == SECRET

    async def test_migration_is_idempotent(self):
        from src.orbi_dev.migrations import migrate_legacy_secrets

        await self._legacy_integration()
        await migrate_legacy_secrets()

        assert await migrate_legacy_secrets() == 0
        assert await IntegrationSecret.find().count() == 1

    async def test_existing_new_secret_is_never_overwritten(self):
        from src.orbi_dev.migrations import migrate_legacy_secrets

        integration = await self._legacy_integration()
        newer = encrypt_secret("newer_secret_value_987654")
        await IntegrationSecret(integration_id=str(integration.id), owner_id=ALICE, ciphertext=newer).insert()

        await migrate_legacy_secrets()

        assert await service.get_secret_ciphertext(ALICE, str(integration.id)) == newer

    async def test_revoked_legacy_integration_loses_its_secret_without_copy(self):
        from src.orbi_dev.migrations import migrate_legacy_secrets

        integration = await self._legacy_integration(status="revoked")

        await migrate_legacy_secrets()

        raw = await Integration.get_pymongo_collection().find_one({"_id": integration.id})
        assert "secret_ciphertext" not in raw
        assert await service.get_secret_ciphertext(ALICE, str(integration.id)) is None

    async def test_revoke_erases_a_leftover_legacy_field(self):
        integration = await self._legacy_integration()

        await service.revoke_integration(ALICE, str(integration.id))

        raw = await Integration.get_pymongo_collection().find_one({"_id": integration.id})
        assert "secret_ciphertext" not in raw
