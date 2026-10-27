"""Notifications Telegram de fin d'exécution Orbi Dev : un destinataire (le propriétaire), une fois, sans fuite."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import Forbidden, NetworkError

from src.models.user import NotificationPreferences, User
from src.orbi_dev import notifier, service
from src.orbi_dev.models import Execution
from src.orbi_dev.state import ExecutionStatus

REPO = "https://github.com/acme/demo"
EVIL = '<a href="https://evil.example">gagnez</a>'


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    from cryptography.fernet import Fernet

    from src.core.config import get_settings

    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()


async def admin(telegram_id: int, **kw) -> User:
    return await User(telegram_id=telegram_id, first_name=f"u{telegram_id}", role="admin", **kw).insert()


async def finished(owner: int, status: ExecutionStatus, *, prompt="Ajoute un test", project="demo", **fields) -> Execution:
    p = await service.create_project(owner, project, REPO)
    i = await service.create_integration(owner, "fake", "k", label=f"i{owner}{prompt[:3]}")
    task = await service.create_task(owner, str(p.id), str(i.id), prompt)
    ex = await service.create_execution(owner, str(task.id))
    await Execution.get_pymongo_collection().update_one(
        {"_id": ex.id}, {"$set": {"status": status.value, "updated_at": datetime.now(UTC), **fields}}
    )
    return await Execution.get(ex.id)


def bot() -> MagicMock:
    b = MagicMock()
    b.send_message = AsyncMock()
    return b


class TestWhoReceivesWhat:
    async def test_each_owner_only_gets_their_own_runs(self):
        await admin(1)
        await admin(2)
        await finished(1, ExecutionStatus.SUCCEEDED, prompt="Tâche de un", project="projet-un", result_summary="fait par un")
        await finished(2, ExecutionStatus.FAILED, prompt="Tâche de deux", project="projet-deux", error_message="boum")
        b = bot()

        assert await notifier.notify_pending(b) == 2

        sent = {c.kwargs["chat_id"]: c.kwargs["text"] for c in b.send_message.await_args_list}
        assert set(sent) == {1, 2}
        assert "projet-un" in sent[1] and "Tâche de un" in sent[1] and "deux" not in sent[1]
        assert "projet-deux" in sent[2] and "boum" in sent[2] and "un" not in sent[2].replace("Tâche de deux", "")

    async def test_each_final_state_is_announced_once(self):
        await admin(1)
        await finished(1, ExecutionStatus.SUCCEEDED)
        b = bot()
        assert await notifier.notify_pending(b) == 1
        assert await notifier.notify_pending(b) == 0
        assert b.send_message.await_count == 1

    async def test_concurrent_passes_cannot_double_send(self):
        import asyncio

        await admin(1)
        await finished(1, ExecutionStatus.SUCCEEDED)
        b = bot()
        results = await asyncio.gather(*(notifier.notify_pending(b) for _ in range(5)))
        assert sum(results) == 1 and b.send_message.await_count == 1

    async def test_the_announcement_of_a_state_can_only_be_claimed_once(self):
        """Deux passages qui ont lu la même exécution : un seul obtient le droit d'envoyer."""
        await admin(1)
        ex = await finished(1, ExecutionStatus.SUCCEEDED)
        assert await notifier._claim(ex) is not None
        assert await notifier._claim(ex) is None

    async def test_a_claim_is_void_if_the_state_changed_meanwhile(self):
        await admin(1)
        ex = await finished(1, ExecutionStatus.NEEDS_ATTENTION)
        await Execution.get_pymongo_collection().update_one({"_id": ex.id}, {"$set": {"status": "running"}})
        assert await notifier._claim(ex) is None

    async def test_only_final_or_attention_states_are_announced(self):
        await admin(1)
        for n, status in enumerate((ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, ExecutionStatus.CANCELLED)):
            await finished(1, status, prompt=f"t{n}")
        b = bot()
        assert await notifier.notify_pending(b) == 0

    async def test_old_executions_are_never_announced(self):
        await admin(1)
        await finished(1, ExecutionStatus.SUCCEEDED, updated_at=datetime.now(UTC) - timedelta(hours=7))
        b = bot()
        assert await notifier.notify_pending(b) == 0 and not b.send_message.await_count

    async def test_muted_banned_or_unprivileged_users_get_nothing_and_are_not_retried(self):
        await admin(1, enabled_notifications=[NotificationPreferences.TICKET_REPLIES])
        await admin(2, is_banned=True)
        await finished(1, ExecutionStatus.SUCCEEDED, prompt="a")
        await finished(2, ExecutionStatus.SUCCEEDED, prompt="b")
        b = bot()
        assert await notifier.notify_pending(b) == 0
        assert not b.send_message.await_count
        # rallumer la préférence ne déclenche pas un message pour un état déjà traité
        user = await User.find_one(User.telegram_id == 1)
        user.enabled_notifications.append(NotificationPreferences.DEV_RUNS)
        await user.save()
        assert await notifier.notify_pending(b) == 0


class TestDelivery:
    async def test_user_content_is_escaped_for_html(self):
        await admin(1)
        await finished(1, ExecutionStatus.FAILED, prompt=EVIL, project="<b>x</b>", error_message="<script>1</script>")
        b = bot()
        await notifier.notify_pending(b)
        text = b.send_message.await_args.kwargs["text"]
        for raw in ("<a href", "<script>", "<b>x</b>"):
            assert raw not in text
        assert "&lt;a href" in text

    async def test_blocked_bot_is_not_retried(self):
        await admin(1)
        await finished(1, ExecutionStatus.SUCCEEDED)
        b = bot()
        b.send_message.side_effect = Forbidden("bot was blocked by the user")
        await notifier.notify_pending(b)
        await notifier.notify_pending(b)
        assert b.send_message.await_count == 1

    async def test_transient_failure_is_retried_then_given_up(self):
        await admin(1)
        ex = await finished(1, ExecutionStatus.SUCCEEDED)
        b = bot()
        b.send_message.side_effect = NetworkError("down")
        for _ in range(notifier.MAX_ATTEMPTS + 3):
            await notifier.notify_pending(b)
        assert b.send_message.await_count == notifier.MAX_ATTEMPTS
        assert (await Execution.get(ex.id)).notify_attempts == notifier.MAX_ATTEMPTS

        ok = bot()  # le réseau revient pour une autre exécution : elle part normalement
        await finished(1, ExecutionStatus.SUCCEEDED, prompt="autre")
        assert await notifier.notify_pending(ok) == 1

    async def test_recovery_after_a_transient_failure(self):
        await admin(1)
        await finished(1, ExecutionStatus.SUCCEEDED)
        b = bot()
        b.send_message.side_effect = [NetworkError("down"), None]
        assert await notifier.notify_pending(b) == 0
        assert await notifier.notify_pending(b) == 1


class TestKeyboard:
    def ex(self, status, **kw) -> Execution:
        return Execution(
            owner_id=1, task_id="t", integration_id="i", provider="fake", status=status, idempotency_key="k",
            client_ref="r", **kw,
        )

    def buttons(self, markup):
        return [b for row in markup.inline_keyboard for b in row] if markup else []

    def test_retry_only_after_a_failure(self):
        for status, expected in ((ExecutionStatus.FAILED, "devx:retry:"), (ExecutionStatus.TIMED_OUT, "devx:retry:"),
                                 (ExecutionStatus.NEEDS_ATTENTION, "devx:check:")):
            data = [b.callback_data for b in self.buttons(notifier.build_keyboard(self.ex(status)))]
            assert any(d and d.startswith(expected) for d in data), status
        assert not any(b.callback_data for b in self.buttons(notifier.build_keyboard(self.ex(ExecutionStatus.SUCCEEDED))))

    def test_pull_request_link_must_be_https(self):
        good = notifier.build_keyboard(self.ex(ExecutionStatus.SUCCEEDED, pr_url="https://github.com/a/b/pull/1"))
        assert [b.url for b in self.buttons(good)] == ["https://github.com/a/b/pull/1"]
        for bad in ("javascript:alert(1)", "http://github.com/a/b/pull/1", "https://x y"):
            assert notifier.build_keyboard(self.ex(ExecutionStatus.SUCCEEDED, pr_url=bad)) is None

    def test_mini_app_button_needs_a_public_https_url(self, monkeypatch):
        from src.core.config import get_settings

        monkeypatch.setenv("BASE_URL", "https://orbi.example.org")
        get_settings.cache_clear()
        markup = notifier.build_keyboard(self.ex(ExecutionStatus.SUCCEEDED))
        assert self.buttons(markup)[0].web_app.url.startswith("https://orbi.example.org/dev/executions/")
        monkeypatch.setenv("BASE_URL", "http://localhost:8000")
        get_settings.cache_clear()
        assert notifier.build_keyboard(self.ex(ExecutionStatus.SUCCEEDED)) is None

    def test_action_can_be_dropped(self):
        markup = notifier.build_keyboard(self.ex(ExecutionStatus.FAILED), with_action=False)
        assert not any(b.callback_data for b in self.buttons(markup))


def _query(user_id: int, data: str) -> tuple[MagicMock, MagicMock]:
    query = MagicMock()
    query.data = data
    query.from_user.id = user_id
    query.answer = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    return update, query


class TestButtons:
    def ctx(self, user: User | None) -> MagicMock:
        context = MagicMock()
        context.user_data = {"db_user": user}
        context.application.create_task = lambda coro: coro.close()  # le lancement réel est testé ailleurs
        return context

    async def test_retry_creates_the_next_attempt_for_the_owner(self):
        from src.handlers.orbi_dev import retry_execution

        user = await admin(1)
        ex = await finished(1, ExecutionStatus.FAILED)
        update, query = _query(1, f"devx:retry:{ex.id}")
        await retry_execution(update, self.ctx(user))
        assert await Execution.find(Execution.task_id == ex.task_id).count() == 2
        assert "lancée" in query.answer.await_args.args[0]
        query.edit_message_reply_markup.assert_awaited_once()

    async def test_double_click_does_not_launch_twice(self):
        from src.handlers.orbi_dev import retry_execution

        user = await admin(1)
        ex = await finished(1, ExecutionStatus.FAILED)
        for _ in range(2):
            update, query = _query(1, f"devx:retry:{ex.id}")
            await retry_execution(update, self.ctx(user))
        assert await Execution.find(Execution.task_id == ex.task_id).count() == 2
        assert query.answer.await_args.kwargs.get("show_alert") is True

    async def test_someone_else_cannot_act_on_a_forwarded_message(self):
        from src.handlers.orbi_dev import check_execution, retry_execution

        await admin(1)
        other = await admin(2)
        ex = await finished(1, ExecutionStatus.FAILED)
        for handler, prefix in ((retry_execution, "devx:retry:"), (check_execution, "devx:check:")):
            update, query = _query(2, f"{prefix}{ex.id}")
            await handler(update, self.ctx(other))
            assert query.answer.await_args.kwargs.get("show_alert") is True
        assert await Execution.find(Execution.task_id == ex.task_id).count() == 1

    async def test_users_without_access_are_refused(self):
        from src.handlers.orbi_dev import retry_execution

        plain = await User(telegram_id=3, first_name="x").insert()
        update, query = _query(3, "devx:retry:abc")
        await retry_execution(update, self.ctx(plain))
        assert query.answer.await_args.args[0] == "Accès refusé."

    async def test_check_refreshes_a_needs_attention_run(self):
        from src.handlers.orbi_dev import check_execution

        user = await admin(1)
        ex = await finished(1, ExecutionStatus.NEEDS_ATTENTION)
        update, query = _query(1, f"devx:check:{ex.id}")
        await check_execution(update, self.ctx(user))
        assert "Vérification" in query.answer.await_args.args[0]


class TestWorkerAndMigration:
    async def test_worker_pass_announces_when_the_bot_is_ready(self):
        from src.orbi_dev import worker

        await admin(1)
        await finished(1, ExecutionStatus.SUCCEEDED)
        b = bot()
        await worker.run_once(b)
        assert b.send_message.await_count == 1

    async def test_worker_pass_without_a_bot_leaves_the_announcement_for_later(self):
        from src.orbi_dev import worker

        await admin(1)
        await finished(1, ExecutionStatus.SUCCEEDED)
        await worker.run_once(None)
        b = bot()
        assert await notifier.notify_pending(b) == 1

    async def test_migration_enables_once_and_respects_later_opt_out(self):
        from src.orbi_dev.migrations import enable_dev_run_notifications_once

        await User(telegram_id=9, first_name="old", enabled_notifications=["morning_brief"]).insert()
        assert await enable_dev_run_notifications_once() == 1
        user = await User.find_one(User.telegram_id == 9)
        assert NotificationPreferences.DEV_RUNS in user.enabled_notifications
        user.enabled_notifications.remove(NotificationPreferences.DEV_RUNS)
        await user.save()
        assert await enable_dev_run_notifications_once() == 0
        assert NotificationPreferences.DEV_RUNS not in (await User.find_one(User.telegram_id == 9)).enabled_notifications

    async def test_migrations_run_at_application_startup(self):
        """scripts/init_db.py n'est lancé par aucun déploiement : l'application doit migrer elle-même."""
        import inspect

        import src.main as main

        assert "run_migrations()" in inspect.getsource(main.lifespan)
