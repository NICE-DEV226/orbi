"""Tests du routage CI → tâche Orbi Dev et de l'approbation humaine (ADR-0009)."""

import pytest
from cryptography.fernet import Fernet

from src.core.config import get_settings
from src.models.developer import GithubWebhookLog
from src.orbi_dev import runner, service
from src.orbi_dev.ci import build_ci_prompt, route_ci_event, source_ref_for
from src.orbi_dev.models import Execution, Task
from src.orbi_dev.state import ExecutionStatus

ALICE, BOB = 1001, 2002
SECRET = "key_super_secret_value_123456"
REPO = "acme/demo"


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()


def _ci_log(conclusion="failure", repository=REPO, event_type="check_run", delivery="d-1") -> GithubWebhookLog:
    return GithubWebhookLog(
        event_type=event_type,
        action="completed",
        repository=repository,
        sender="octocat",
        payload_details={
            "conclusion": conclusion,
            "check_name": "tests",
            "sha": "abc123",
            "url": "https://github.com/acme/demo/runs/1",
        },
        delivery_id=delivery,
    )


async def _project_with_integration(owner=ALICE, repo_url="https://github.com/acme/demo"):
    project = await service.create_project(owner, "demo", repo_url)
    integration = await service.create_integration(owner, "fake", SECRET, capabilities=["launch"])
    return project, integration


class TestCiRouting:
    async def test_failure_creates_a_task_awaiting_approval(self):
        project, _ = await _project_with_integration()

        assert await route_ci_event(_ci_log()) == 1

        task = (await Task.find(Task.owner_id == ALICE).to_list())[0]
        assert task.project_id == str(project.id)
        assert task.source_ref == source_ref_for(REPO, "abc123", "tests")
        assert "acme/demo" in task.prompt and "abc123" in task.prompt
        assert "https://github.com/acme/demo/runs/1" in task.prompt

        execution = (await service.list_executions(ALICE))[0]
        assert execution.status == ExecutionStatus.AWAITING_APPROVAL

    async def test_same_failure_is_not_duplicated(self):
        await _project_with_integration()

        assert await route_ci_event(_ci_log(delivery="d-1")) == 1
        assert await route_ci_event(_ci_log(delivery="d-2")) == 0  # autre livraison, même source
        assert await Task.find(Task.owner_id == ALICE).count() == 1

    async def test_different_check_on_same_commit_is_a_new_task(self):
        await _project_with_integration()
        other = _ci_log(delivery="d-2")
        other.payload_details["check_name"] = "lint"

        assert await route_ci_event(_ci_log()) == 1
        assert await route_ci_event(other) == 1
        assert await Task.find(Task.owner_id == ALICE).count() == 2

    async def test_success_and_non_ci_events_are_ignored(self):
        await _project_with_integration()

        assert await route_ci_event(_ci_log(conclusion="success")) == 0
        assert await route_ci_event(_ci_log(event_type="push")) == 0
        assert await Task.find(Task.owner_id == ALICE).count() == 0

    async def test_project_without_github_repo_is_ignored(self):
        await _project_with_integration(repo_url="https://gitlab.com/acme/demo")

        assert await route_ci_event(_ci_log()) == 0

    async def test_archived_project_is_ignored(self):
        project, _ = await _project_with_integration()
        await service.archive_project(ALICE, str(project.id))

        assert await route_ci_event(_ci_log()) == 0

    async def test_owner_without_active_integration_gets_nothing(self):
        await service.create_project(ALICE, "demo", "https://github.com/acme/demo")

        assert await route_ci_event(_ci_log()) == 0
        assert await Task.find(Task.owner_id == ALICE).count() == 0

    async def test_each_owner_tracking_the_repo_gets_its_own_task(self):
        await _project_with_integration(ALICE)
        await _project_with_integration(BOB)

        assert await route_ci_event(_ci_log()) == 2
        assert await Task.find(Task.owner_id == ALICE).count() == 1
        assert await Task.find(Task.owner_id == BOB).count() == 1

    def test_prompt_is_a_template_without_raw_logs(self):
        prompt = build_ci_prompt(REPO, "tests", "abc123", "https://x")
        assert "acme/demo" in prompt and "abc123" in prompt and "https://x" in prompt
        assert "pull request" in prompt


class TestApproval:
    async def _awaiting(self, owner=ALICE):
        project = await service.create_project(owner, "demo", "https://github.com/acme/demo")
        integration = await service.create_integration(owner, "fake", SECRET, capabilities=["launch"])
        task = await service.create_task(owner, str(project.id), str(integration.id), "Corrige")
        return await service.create_execution(owner, str(task.id), requires_approval=True)

    async def test_approve_moves_to_queued_then_launches(self):
        execution = await self._awaiting()

        approved = await runner.approve_execution(ALICE, str(execution.id))
        assert approved.status == ExecutionStatus.QUEUED

        running = await runner.launch_execution(ALICE, str(execution.id))
        assert running.status in (ExecutionStatus.RUNNING, ExecutionStatus.SUCCEEDED)

    async def test_approve_twice_is_refused(self):
        execution = await self._awaiting()
        await runner.approve_execution(ALICE, str(execution.id))

        with pytest.raises(service.ConflictError):
            await runner.approve_execution(ALICE, str(execution.id))

    async def test_dismiss_cancels_without_launching(self):
        execution = await self._awaiting()

        dismissed = await runner.dismiss_execution(ALICE, str(execution.id))
        assert dismissed.status == ExecutionStatus.CANCELLED

        with pytest.raises(service.ConflictError):
            await runner.approve_execution(ALICE, str(execution.id))

    async def test_other_owner_cannot_approve(self):
        execution = await self._awaiting()

        with pytest.raises(service.NotFoundError):
            await runner.approve_execution(BOB, str(execution.id))


class TestApprovalKeyboard:
    def test_awaiting_approval_offers_launch_and_ignore(self):
        from src.orbi_dev.notifier import CB_APPROVE, CB_IGNORE, build_keyboard

        execution = Execution(
            owner_id=ALICE, task_id="t", integration_id="i", provider="fake",
            status=ExecutionStatus.AWAITING_APPROVAL, idempotency_key="k", client_ref="c",
        )
        keyboard = build_keyboard(execution)
        callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
        assert f"{CB_APPROVE}{execution.id}" in callbacks
        assert f"{CB_IGNORE}{execution.id}" in callbacks
