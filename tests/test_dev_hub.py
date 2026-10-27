"""Orbi Dev dans Telegram : accueil, création de tâche dans le chat, carte de suivi, isolement entre utilisateurs."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest, NetworkError

from src.handlers import dev_hub
from src.models.user import User
from src.orbi_dev import cards, service
from src.orbi_dev.models import Execution, Project, Task
from src.orbi_dev.repo import parse_repo
from src.orbi_dev.state import ExecutionStatus

REPO = "https://github.com/acme/demo"


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    from cryptography.fernet import Fernet

    from src.core.config import get_settings

    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()


async def admin(telegram_id: int) -> User:
    return await User(telegram_id=telegram_id, first_name=f"u{telegram_id}", role="admin").insert()


class Chat:
    """Un utilisateur qui parle au bot : fabrique des updates et retient ce que le bot affiche."""

    def __init__(self, user: User):
        self.user = user
        self.launched = 0
        self.context = MagicMock()
        self.context.user_data = {"db_user": user}
        self.context.args = []
        self.context.application.create_task = self._launch
        self.shown: list[str] = []
        self.markups: list = []
        self.alerts: list[str] = []

    def _launch(self, coro):
        self.launched += 1
        coro.close()

    def _record(self, text, reply_markup=None, **_):
        self.shown.append(text)
        self.markups.append(reply_markup)

    def button(self, data: str):
        query = MagicMock()
        query.data = data
        query.message.photo = ()
        query.message.chat_id = self.user.telegram_id
        query.message.message_id = 700
        query.edit_message_text = AsyncMock(side_effect=self._record)
        query.answer = AsyncMock(side_effect=lambda text=None, show_alert=False: self.alerts.append(text) if text else None)
        update = MagicMock()
        update.callback_query = query
        update.effective_user.id = self.user.telegram_id
        update.message = None
        return update

    def message(self, text: str):
        update = MagicMock()
        update.callback_query = None
        update.effective_user.id = self.user.telegram_id
        update.message.text = text
        update.message.reply_text = AsyncMock(side_effect=self._record)
        update.effective_message = update.message
        return update

    async def press(self, handler, data: str):
        await handler(self.button(data), self.context)

    async def say(self, handler, text: str):
        await handler(self.message(text), self.context)

    @property
    def last(self) -> str:
        return self.shown[-1]

    def last_buttons(self) -> list[str]:
        markup = self.markups[-1]
        return [b.text for row in markup.inline_keyboard for b in row] if markup else []

    def last_data(self) -> list[str]:
        markup = self.markups[-1]
        return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data] if markup else []


async def setup_workspace(owner: int, *, projects: int = 1, providers: int = 1):
    for n in range(projects):
        await service.create_project(owner, f"demo{n}", f"{REPO}{n}")
    for n in range(providers):
        await service.create_integration(owner, "fake", f"k{n}", label=f"agent{n}")


class TestRepoParsing:
    @pytest.mark.parametrize("text,url,branch", [
        ("https://github.com/acme/demo", REPO, ""),
        ("github.com/acme/demo.git", REPO, ""),
        ("acme/demo", REPO, ""),
        ("https://github.com/acme/demo/", REPO, ""),
        ("https://github.com/acme/demo/tree/feat/x", REPO, "feat/x"),
        ("  https://github.com/acme/demo?tab=readme  ", REPO, ""),
    ])
    def test_accepts_what_people_copy(self, text, url, branch):
        repo = parse_repo(text)
        assert repo is not None and repo.url == url and repo.branch == branch and repo.name == "demo"

    @pytest.mark.parametrize("text", [
        "", "demo", "http://evil.example/acme/demo", "https://gitlab.com/acme/demo", "a/b/c", "../x", "javascript:alert(1)",
        "https://github.com/acme", "x" * 400,
    ])
    def test_refuses_everything_else(self, text):
        assert parse_repo(text) is None


class TestAccess:
    async def test_plain_users_get_nothing(self):
        plain = await User(telegram_id=5, first_name="x").insert()
        chat = Chat(plain)
        await chat.say(dev_hub.task_command, "/task fais ceci")
        assert "réservé" in chat.last
        await chat.press(dev_hub.show_home, "dv:home")
        assert any("réservé" in a for a in chat.alerts)
        assert await Task.find().count() == 0

    async def test_text_is_ignored_without_a_flow(self):
        chat = Chat(await admin(1))
        await chat.say(dev_hub.on_text, "salut")
        assert chat.shown == []


class TestHome:
    async def test_empty_account_gets_a_checklist(self):
        chat = Chat(await admin(1))
        await chat.press(dev_hub.show_home, "dv:home")
        assert "Pour commencer" in chat.last
        assert chat.last.count("⬜") == 3
        assert "dv:newrepo" in chat.last_data()

    async def test_checklist_ticks_what_is_done(self):
        await service.create_integration(1, "fake", "k")
        chat = Chat(await admin(1))
        await chat.press(dev_hub.show_home, "dv:home")
        assert "✅ Connecter un fournisseur" in chat.last and "⬜ Ajouter un dépôt" in chat.last

    async def test_board_counts_active_and_attention_runs(self):
        await setup_workspace(1)
        project = (await service.list_projects(1))[0]
        integration = (await service.list_integrations(1))[0]
        for status in (ExecutionStatus.RUNNING, ExecutionStatus.NEEDS_ATTENTION, ExecutionStatus.SUCCEEDED):
            task = await service.create_task(1, str(project.id), str(integration.id), f"tâche {status.value}")
            ex = await service.create_execution(1, str(task.id))
            await Execution.get_pymongo_collection().update_one({"_id": ex.id}, {"$set": {"status": status.value}})
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.show_home, "dv:home")
        assert "1 en cours" in chat.last and "1 à vérifier" in chat.last
        assert "tâche succeeded" in chat.last
        assert {"dv:new", "dv:list", "dv:projects", "nav:more"} <= set(chat.last_data())

    async def test_board_only_shows_my_runs(self):
        await admin(2)
        await setup_workspace(2)
        project = (await service.list_projects(2))[0]
        integration = (await service.list_integrations(2))[0]
        await service.create_task(2, str(project.id), str(integration.id), "secret d'un autre")
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.show_home, "dv:home")
        assert "secret d'un autre" not in chat.last

    async def test_untrusted_text_is_escaped(self):
        await setup_workspace(1)
        project = (await service.list_projects(1))[0]
        integration = (await service.list_integrations(1))[0]
        task = await service.create_task(1, str(project.id), str(integration.id), "<b>gras</b> & <a href='x'>l</a>")
        ex = await service.create_execution(1, str(task.id))
        await Execution.get_pymongo_collection().update_one({"_id": ex.id}, {"$set": {"status": "running"}})
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.show_home, "dv:home")
        assert "<a href" not in chat.last and "&lt;b&gt;" in chat.last


async def admin_user(telegram_id: int) -> User:
    return await User.find_one(User.telegram_id == telegram_id) or await admin(telegram_id)


class TestCreateTask:
    async def test_full_flow_ends_with_a_running_card(self):
        await admin(1)
        await setup_workspace(1)
        chat = Chat(await admin_user(1))

        await chat.press(dev_hub.start_task, "dv:new")  # un seul projet, un seul fournisseur : on passe direct à la consigne
        assert "Que faut-il faire sur" in chat.last
        await chat.say(dev_hub.on_text, "Ajoute un test pour le login")
        assert "Lancer cette tâche" in chat.last and "Ajoute un test pour le login" in chat.last
        assert "dv:go" in chat.last_data()
        assert await Task.find().count() == 0  # rien n'existe avant « Lancer »

        await chat.press(dev_hub.launch, "dv:go")
        assert chat.launched == 1
        task = await Task.find_one()
        assert task.prompt == "Ajoute un test pour le login" and task.owner_id == 1
        ex = await Execution.find_one()
        assert ex.card_chat_id == 1 and ex.card_message_id == 700 and ex.card_status == "queued"
        assert "En attente" in chat.last

    async def test_double_click_on_launch_creates_one_task(self):
        await admin(1)
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        await chat.say(dev_hub.on_text, "Fais ceci")
        await chat.press(dev_hub.launch, "dv:go")
        await chat.press(dev_hub.launch, "dv:go")
        assert await Task.find().count() == 1 and chat.launched == 1
        assert any("expiré" in a for a in chat.alerts)

    async def test_task_command_uses_last_project_and_asks_for_confirmation(self):
        await admin(1)
        await setup_workspace(1, projects=2)
        projects = {p.name: p for p in await service.list_projects(1)}
        integration = (await service.list_integrations(1))[0]
        await service.create_task(1, str(projects["demo1"].id), str(integration.id), "ancienne tâche")
        chat = Chat(await admin_user(1))
        chat.context.args = ["Corrige", "le", "bug"]
        await chat.say(dev_hub.task_command, "/task Corrige le bug")
        assert "Lancer cette tâche" in chat.last and "demo1" in chat.last and "Corrige le bug" in chat.last
        assert await Task.find().count() == 1  # pas de lancement sans confirmation

    async def test_several_projects_are_offered_last_used_first(self):
        await admin(1)
        await setup_workspace(1, projects=3)
        projects = {p.name: p for p in await service.list_projects(1)}
        integration = (await service.list_integrations(1))[0]
        await service.create_task(1, str(projects["demo2"].id), str(integration.id), "x")
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        assert "Quel projet" in chat.last
        assert chat.last_buttons()[0] == "📁 demo2"

    async def test_several_providers_are_offered(self):
        await admin(1)
        await setup_workspace(1, providers=2)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        assert "Quel fournisseur" in chat.last
        data = [d for d in chat.last_data() if d.startswith("dv:i:")]
        await chat.press(dev_hub.pick_provider, data[0])
        assert "Que faut-il faire" in chat.last

    async def test_too_long_prompt_is_refused_and_flow_continues(self):
        await admin(1)
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        await chat.say(dev_hub.on_text, "x" * 8001)
        assert "8000" in chat.last
        await chat.say(dev_hub.on_text, "court")
        assert "Lancer cette tâche" in chat.last

    async def test_cancel_goes_home_and_forgets_the_draft(self):
        await admin(1)
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        await chat.press(dev_hub.discard, "dv:no")
        assert "Orbi Dev" in chat.last
        await chat.say(dev_hub.on_text, "message perdu")
        assert await Task.find().count() == 0

    async def test_expired_draft_is_forgotten(self, monkeypatch):
        await admin(1)
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        chat.context.user_data["dev"]["at"] -= dev_hub.DRAFT_TTL + 5
        await chat.say(dev_hub.on_text, "trop tard")
        assert "Lancer cette tâche" not in chat.last

    async def test_someone_elses_project_cannot_be_picked(self):
        await admin(2)
        await service.create_project(2, "autre", "https://github.com/x/y")
        foreign = (await service.list_projects(2))[0]
        await setup_workspace(1, projects=2)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        await chat.press(dev_hub.pick_project, f"dv:p:{foreign.id}")
        assert any("n'existe plus" in a for a in chat.alerts)
        assert "project_id" not in chat.context.user_data["dev"]

    async def test_revoked_provider_cannot_be_picked(self):
        await admin(1)
        await setup_workspace(1, providers=2)
        revoked = (await service.list_integrations(1))[0]
        from src.orbi_dev import runner

        await runner.revoke_integration(1, str(revoked.id))
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")  # il n'en reste qu'un actif : choisi d'office
        assert "Que faut-il faire" in chat.last
        await chat.press(dev_hub.pick_provider, f"dv:i:{revoked.id}")
        assert any("plus active" in a for a in chat.alerts)


class TestAddRepo:
    async def test_pasted_url_creates_the_project_and_continues_the_task(self):
        await admin(1)
        await service.create_integration(1, "fake", "k")
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        assert "Pour commencer" in chat.last
        await chat.press(dev_hub.ask_repo_for_task, "dv:newrepo")
        assert "Quel dépôt" in chat.last
        await chat.say(dev_hub.on_text, "https://github.com/acme/demo")
        project = await Project.find_one()
        assert project.repo_url == REPO and project.name == "demo" and project.default_branch == ""
        assert "Que faut-il faire sur demo" in chat.last

    async def test_garbage_is_explained_and_asked_again(self):
        chat = Chat(await admin(1))
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(dev_hub.on_text, "n'importe quoi")
        assert "pas reconnu" in chat.last
        assert await Project.find().count() == 0
        await chat.say(dev_hub.on_text, "acme/demo")
        assert await Project.find().count() == 1

    async def test_same_repo_twice_reuses_the_project(self):
        chat = Chat(await admin(1))
        for _ in range(2):
            await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
            await chat.say(dev_hub.on_text, "https://github.com/acme/demo")
        assert await Project.find().count() == 1
        assert "déjà dans vos projets" in chat.last

    async def test_branch_in_the_url_becomes_the_project_branch(self):
        chat = Chat(await admin(1))
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(dev_hub.on_text, "https://github.com/acme/demo/tree/dev")
        assert (await Project.find_one()).default_branch == "dev"


class TestListAndCard:
    async def test_list_opens_a_run_and_never_someone_elses(self):
        await admin(2)
        await setup_workspace(2)
        project, integration = (await service.list_projects(2))[0], (await service.list_integrations(2))[0]
        task = await service.create_task(2, str(project.id), str(integration.id), "privé")
        foreign = await service.create_execution(2, str(task.id))

        await setup_workspace(1)
        project, integration = (await service.list_projects(1))[0], (await service.list_integrations(1))[0]
        task = await service.create_task(1, str(project.id), str(integration.id), "ma tâche")
        mine = await service.create_execution(1, str(task.id))

        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.show_list, "dv:list")
        assert any("ma tâche" in b for b in chat.last_buttons()) and not any("privé" in b for b in chat.last_buttons())
        await chat.press(dev_hub.show_execution, f"dv:e:{mine.id}")
        assert "ma tâche" in chat.last and "dv:list" in chat.last_data()
        await chat.press(dev_hub.show_execution, f"dv:e:{foreign.id}")
        assert any("introuvable" in a for a in chat.alerts)


async def run_with_card(status: ExecutionStatus = ExecutionStatus.QUEUED, **fields) -> Execution:
    await setup_workspace(1)
    project, integration = (await service.list_projects(1))[0], (await service.list_integrations(1))[0]
    task = await service.create_task(1, str(project.id), str(integration.id), "Ajoute un test")
    ex = await service.create_execution(1, str(task.id))
    await cards.attach(ex, 1, 55)
    await Execution.get_pymongo_collection().update_one(
        {"_id": ex.id}, {"$set": {"status": status.value, "updated_at": datetime.now(UTC), **fields}}
    )
    return await Execution.get(ex.id)


def bot(**kwargs) -> MagicMock:
    b = MagicMock()
    b.edit_message_text = AsyncMock(**kwargs)
    return b


class TestCardUpdates:
    async def test_card_follows_the_status_and_edits_once_per_state(self):
        await admin(1)
        ex = await run_with_card(ExecutionStatus.RUNNING)
        b = bot()
        assert await cards.update_cards(b) == 1
        sent = b.edit_message_text.await_args.kwargs
        assert sent["chat_id"] == 1 and sent["message_id"] == 55
        assert "En cours" in sent["text"] and "Ajoute un test" in sent["text"]
        assert await cards.update_cards(b) == 0  # même état : rien de plus
        await Execution.get_pymongo_collection().update_one(
            {"_id": ex.id}, {"$set": {"status": "succeeded", "result_summary": "PR ouverte", "updated_at": datetime.now(UTC)}}
        )
        assert await cards.update_cards(b) == 1
        assert "Terminé" in b.edit_message_text.await_args.kwargs["text"]

    async def test_concurrent_passes_edit_only_once(self):
        await admin(1)
        ex = await run_with_card(ExecutionStatus.RUNNING)
        assert await cards._claim(ex) is not None
        assert await cards._claim(ex) is None

    async def test_card_text_is_escaped(self):
        await admin(1)
        ex = await run_with_card(ExecutionStatus.FAILED, error_message='<a href="https://evil.example">x</a>')
        text, _ = await cards.render(ex)
        assert "<a href" not in text and "&lt;a href" in text

    async def test_transient_failure_retries_then_gives_up(self):
        await admin(1)
        ex = await run_with_card(ExecutionStatus.RUNNING)
        failing = bot(side_effect=NetworkError("réseau"))
        for _ in range(cards.MAX_ATTEMPTS + 2):
            await cards.update_cards(failing)
        assert failing.edit_message_text.await_count == cards.MAX_ATTEMPTS
        assert (await Execution.get(ex.id)).card_attempts == cards.MAX_ATTEMPTS

    async def test_deleted_card_is_abandoned(self):
        await admin(1)
        ex = await run_with_card(ExecutionStatus.RUNNING)
        gone = bot(side_effect=BadRequest("Message to edit not found"))
        await cards.update_cards(gone)
        await cards.update_cards(gone)
        assert gone.edit_message_text.await_count == 1
        assert (await Execution.get(ex.id)).card_message_id is None

    async def test_not_modified_is_not_an_error(self):
        await admin(1)
        await run_with_card(ExecutionStatus.RUNNING)
        same = bot(side_effect=BadRequest("Message is not modified"))
        assert await cards.update_cards(same) == 1

    async def test_old_cards_are_left_alone(self):
        await admin(1)
        await run_with_card(ExecutionStatus.RUNNING, updated_at=datetime.now(UTC) - timedelta(hours=7))
        b = bot()
        assert await cards.update_cards(b) == 0

    async def test_active_card_has_refresh_and_finished_card_has_no_action(self):
        await admin(1)
        ex = await run_with_card(ExecutionStatus.RUNNING)
        _, kb = await cards.render(ex)
        assert "🔄 Actualiser" in [b.text for row in kb.inline_keyboard for b in row] if kb else False
        done = await run_with_card_status(ex, ExecutionStatus.FAILED)
        _, kb = await cards.render(done)
        labels = [b.text for row in kb.inline_keyboard for b in row] if kb else []
        assert "🔁 Réessayer" not in labels and "🔄 Actualiser" not in labels

    async def test_alert_is_sent_as_a_reply_to_the_card(self):
        from src.orbi_dev import notifier

        await admin(1)
        await run_with_card(ExecutionStatus.SUCCEEDED, result_summary="fait")
        b = MagicMock()
        b.send_message = AsyncMock()
        await notifier.notify_pending(b)
        assert b.send_message.await_args.kwargs["reply_parameters"].message_id == 55


async def run_with_card_status(ex: Execution, status: ExecutionStatus) -> Execution:
    await Execution.get_pymongo_collection().update_one({"_id": ex.id}, {"$set": {"status": status.value}})
    return await Execution.get(ex.id)


class TestMenus:
    async def test_admin_home_is_orbi_dev_and_other_modules_are_behind_more(self):
        from src.bot.keyboards import main_menu_keyboard

        keyboard = main_menu_keyboard("fr", is_admin=True)
        first = keyboard.inline_keyboard[0]
        assert first[0].callback_data == "dv:home"
        plain = main_menu_keyboard("fr", is_admin=False)
        assert all(b.callback_data != "dv:home" for row in plain.inline_keyboard for b in row)

    async def test_nav_home_opens_orbi_dev_for_admins_only(self):
        from src.handlers import menu

        chat = Chat(await admin(1))
        await chat.press(menu.show_main_menu, "nav:home")
        assert "Orbi Dev" in chat.last
