"""Boutons du bot qui ne répondaient pas : écrans ouverts depuis le menu photo, requêtes Beanie invalides, erreurs muettes."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest

from src.bot.errors import USER_MESSAGE, on_error
from src.bot.screen import edit_screen
from src.models.productivity import Task, TaskStatus
from src.models.ticket import Ticket, TicketCategory, TicketStatus

SRC = Path(__file__).resolve().parent.parent / "src"


def _query(*, photo: bool) -> MagicMock:
    query = MagicMock()
    query.message.photo = (MagicMock(),) if photo else ()
    query.message.chat_id = 42
    query.edit_message_text = AsyncMock()
    query.delete_message = AsyncMock()
    query.get_bot.return_value.send_message = AsyncMock()
    return query


class TestEditScreen:
    async def test_text_message_is_edited_in_place(self):
        query = _query(photo=False)
        await edit_screen(query, "Salut", reply_markup="kb")
        query.edit_message_text.assert_awaited_once_with("Salut", reply_markup="kb")
        query.delete_message.assert_not_awaited()

    async def test_photo_message_is_replaced_by_a_text_message(self):
        """Le menu principal est une photo : éditer son texte lève « There is no text in the message to edit »."""
        query = _query(photo=True)
        await edit_screen(query, "Salut", reply_markup="kb")
        query.edit_message_text.assert_not_awaited()
        query.delete_message.assert_awaited_once()
        query.get_bot.return_value.send_message.assert_awaited_once_with(chat_id=42, text="Salut", reply_markup="kb")

    async def test_photo_deletion_failure_still_shows_the_screen(self):
        query = _query(photo=True)
        query.delete_message.side_effect = BadRequest("Message can't be deleted")
        await edit_screen(query, "Salut")
        query.get_bot.return_value.send_message.assert_awaited_once()

    async def test_unchanged_content_is_not_an_error(self):
        query = _query(photo=False)
        query.edit_message_text.side_effect = BadRequest("Message is not modified: ...")
        await edit_screen(query, "Salut")

    async def test_other_telegram_errors_are_raised(self):
        query = _query(photo=False)
        query.edit_message_text.side_effect = BadRequest("Chat not found")
        with pytest.raises(BadRequest):
            await edit_screen(query, "Salut")


class TestErrorHandler:
    async def test_pressed_button_gets_an_answer(self):
        from telegram import Update

        update = MagicMock(spec=Update)
        update.callback_query.answer = AsyncMock()
        context = MagicMock()
        context.error = RuntimeError("boom")
        await on_error(update, context)
        update.callback_query.answer.assert_awaited_once_with(USER_MESSAGE, show_alert=True)

    async def test_non_update_errors_do_not_crash_the_handler(self):
        context = MagicMock()
        context.error = RuntimeError("boom")
        await on_error(None, context)

    async def test_failing_answer_does_not_raise(self):
        from telegram import Update

        update = MagicMock(spec=Update)
        update.callback_query.answer = AsyncMock(side_effect=BadRequest("query is too old"))
        context = MagicMock()
        context.error = RuntimeError("boom")
        await on_error(update, context)

    def test_registered_on_the_application(self):
        from src.bot.errors import register_error_handler

        app = MagicMock()
        register_error_handler(app)
        app.add_error_handler.assert_called_once_with(on_error)


class TestSourceRules:
    def test_handlers_never_edit_text_directly(self):
        """Un écran ouvert depuis le menu photo doit passer par edit_screen."""
        offenders = [
            f"{path.relative_to(SRC)}:{n}"
            for path in (SRC / "handlers").glob("*.py")
            for n, line in enumerate(path.read_text().splitlines(), 1)
            if re.search(r"\.edit_message_text\(", line)
        ]
        assert not offenders

    def test_no_invalid_beanie_field_methods(self):
        """`Model.champ.is_in(...)` n'existe pas dans Beanie 2 (lève « ExpressionField is not callable »)."""
        offenders = [
            str(path.relative_to(SRC))
            for path in SRC.rglob("*.py")
            if re.search(r"\.\w+\.is_in\(", path.read_text())
        ]
        assert not offenders


def _ticket(ticket_id: str, **kw) -> Ticket:
    return Ticket(
        ticket_id=ticket_id, user_telegram_id=kw.pop("user", 1), category=TicketCategory.TECHNICAL,
        subject="s", description="d", **kw,
    )


class TestTicketQueries:
    async def test_sla_breaches_are_found_once(self):
        from src.services.ticket_service import check_sla_breaches

        past, future = datetime.now(UTC) - timedelta(hours=1), datetime.now(UTC) + timedelta(hours=1)
        await _ticket("TKT-1", sla_deadline=past).insert()
        await _ticket("TKT-2", sla_deadline=future).insert()
        await _ticket("TKT-3", sla_deadline=past, status=TicketStatus.CLOSED).insert()

        assert [t.ticket_id for t in await check_sla_breaches()] == ["TKT-1"]
        assert await check_sla_breaches() == []  # déjà marqué : pas d'alerte en double

    async def test_count_and_list_by_status(self):
        from src.services.ticket_service import count_open_tickets, get_user_tickets

        await _ticket("TKT-1").insert()
        await _ticket("TKT-2", status=TicketStatus.WAITING_USER).insert()
        await _ticket("TKT-3", status=TicketStatus.CLOSED).insert()
        await _ticket("TKT-4", user=2).insert()

        assert await count_open_tickets(1) == 2
        assert len(await get_user_tickets(1)) == 3
        assert [t.ticket_id for t in await get_user_tickets(1, status_filter=[TicketStatus.CLOSED])] == ["TKT-3"]


class TestTaskQueries:
    async def test_toggle_completion_both_ways(self):
        from src.services.productivity_service import create_task, toggle_task_completion

        task = await create_task(1, "Écrire")
        task = await toggle_task_completion(task)
        assert task.status == TaskStatus.COMPLETED and task.completed_at is not None
        task = await toggle_task_completion(task)
        assert task.status == TaskStatus.ACTIVE and task.completed_at is None

    async def test_completed_tasks_are_hidden_unless_requested(self):
        from src.services.productivity_service import create_task, get_user_tasks, toggle_task_completion

        await create_task(1, "Ouverte")
        await toggle_task_completion(await create_task(1, "Faite"))

        assert [t.title for t in await get_user_tasks(1)] == ["Ouverte"]
        assert len(await get_user_tasks(1, include_completed=True)) == 2

    async def test_reminders_are_sent_once_for_overdue_active_tasks(self):
        from src.services.productivity_service import create_task, get_pending_reminders, toggle_task_completion

        yesterday = datetime.now(UTC) - timedelta(days=1)
        tomorrow = datetime.now(UTC) + timedelta(days=1)
        late = await create_task(1, "En retard", due_date=yesterday)
        await create_task(1, "Pas encore", due_date=tomorrow)
        await create_task(1, "Sans échéance")
        await toggle_task_completion(await create_task(1, "Déjà faite", due_date=yesterday))

        assert [t.title for t in await get_pending_reminders()] == ["En retard"]

        late.reminder_day_sent = True
        await late.save()
        assert await get_pending_reminders() == []

    async def test_reminder_job_marks_the_task_and_notifies(self, monkeypatch):
        from src.services import notification_service, scheduler
        from src.services.productivity_service import create_task

        await create_task(7, "Rendre le rapport", due_date=datetime.now(UTC) - timedelta(hours=1))
        send = AsyncMock()
        monkeypatch.setattr(notification_service, "send_notification", send)
        monkeypatch.setattr(scheduler, "get_scheduler", lambda: MagicMock(bot=MagicMock()))

        await scheduler._task_reminders_job()
        await scheduler._task_reminders_job()  # deuxième passage : rien de plus

        send.assert_awaited_once()
        assert send.await_args.args[1] == 7
        assert (await Task.find_one(Task.user_telegram_id == 7)).reminder_day_sent is True
