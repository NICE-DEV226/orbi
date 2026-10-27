"""Orbi Dev dans Telegram : accueil, création de tâche dans le chat, carte de suivi, isolement entre utilisateurs."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest, NetworkError

from src.handlers import dev_hub
from src.models.user import User
from src.orbi_dev import cards, service
from src.orbi_dev.inputs import parse_repo
from src.orbi_dev.models import Execution, Project, Task
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
        self.context.bot.set_my_commands = AsyncMock()
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
        assert "Connecter un fournisseur" in chat.last
        assert chat.last.count("○") == 3
        assert "dv:newrepo" in chat.last_data()

    async def test_checklist_ticks_what_is_done(self):
        await service.create_integration(1, "fake", "k")
        chat = Chat(await admin(1))
        await chat.press(dev_hub.show_home, "dv:home")
        assert "✓ Connecter un fournisseur" in chat.last and "○ <b>Ajouter un dépôt</b>" in chat.last  # l'étape suivante ressort

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
        assert "<b>1</b> en cours" in chat.last and "<b>1</b> à vérifier" in chat.last
        assert "tâche succeeded" in chat.last
        assert {"dv:new", "dv:list", "dv:projects", "dv:conn", "dv:set"} <= set(chat.last_data())

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
        assert chat.last_buttons()[0] == "demo2"

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


class FakeGitHub:
    """Remplace la vérification GitHub : jamais d'appel réseau dans les tests."""

    def __init__(self, info):
        self.info = info
        self.asked: list[str] = []

    async def __call__(self, repo, client=None):
        self.asked.append(repo.full_name)
        return self.info


@pytest.fixture
def github(monkeypatch):
    from src.orbi_dev.github import Lookup, RepoInfo

    fake = FakeGitHub(RepoInfo(Lookup.FOUND, default_branch="master", description="Un dépôt", language="Python"))
    monkeypatch.setattr("src.handlers.dev_hub.projects.lookup_repo", fake)
    return fake


class TestAddRepo:
    async def test_nothing_is_created_until_the_user_confirms(self, github):
        chat = Chat(await admin(1))
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(dev_hub.on_text, "https://github.com/acme/demo")
        assert "Ajouter ce dépôt" in chat.last and "acme/demo" in chat.last
        assert "<b>master</b>" in chat.last and "Python" in chat.last and "Un dépôt" in chat.last
        assert await Project.find().count() == 0
        await chat.press(dev_hub.confirm_repo, "dv:repook")
        project = await Project.find_one()
        assert project.repo_url == REPO and project.name == "demo" and project.default_branch == ""
        assert "est ajouté" in chat.last

    async def test_pasted_url_then_continues_the_task(self, github):
        await admin(1)
        await service.create_integration(1, "fake", "k")
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        assert "Ajouter un dépôt" in chat.last  # pas de dépôt : retour à la liste « pour commencer »
        await chat.press(dev_hub.ask_repo_for_task, "dv:newrepo")
        assert "Quel dépôt" in chat.last
        await chat.say(dev_hub.on_text, "https://github.com/acme/demo")
        await chat.press(dev_hub.confirm_repo, "dv:repook")
        assert "Que faut-il faire sur demo" in chat.last

    async def test_address_hidden_in_a_sentence_is_found(self, github):
        chat = Chat(await admin(1))
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(dev_hub.on_text, "Voilà le dépôt : https://github.com/acme/demo, merci !")
        assert github.asked == ["acme/demo"]

    async def test_garbage_is_explained_and_asked_again(self, github):
        chat = Chat(await admin(1))
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(dev_hub.on_text, "n'importe quoi")
        assert "pas reconnu" in chat.last and github.asked == []
        await chat.say(dev_hub.on_text, "acme/demo")
        await chat.press(dev_hub.confirm_repo, "dv:repook")
        assert await Project.find().count() == 1

    async def test_unknown_repo_can_still_be_added_on_purpose(self, github):
        from src.orbi_dev.github import Lookup, RepoInfo

        github.info = RepoInfo(Lookup.NOT_FOUND)
        chat = Chat(await admin(1))
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(dev_hub.on_text, "acme/prive")
        assert "introuvable" in chat.last and "privé" in chat.last
        assert chat.last_buttons()[:2] == ["Ajouter quand même", "Corriger l'adresse"]
        assert await Project.find().count() == 0
        await chat.press(dev_hub.confirm_repo, "dv:repook")
        assert (await Project.find_one()).repo_url == "https://github.com/acme/prive"

    async def test_github_down_does_not_block(self, github):
        from src.orbi_dev.github import Lookup, RepoInfo

        github.info = RepoInfo(Lookup.UNKNOWN)
        chat = Chat(await admin(1))
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(dev_hub.on_text, "acme/demo")
        assert "non vérifié" in chat.last and "Ajouter quand même" in chat.last_buttons()

    async def test_archived_repo_is_flagged(self, github):
        from src.orbi_dev.github import Lookup, RepoInfo

        github.info = RepoInfo(Lookup.FOUND, default_branch="main", archived=True)
        chat = Chat(await admin(1))
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(dev_hub.on_text, "acme/demo")
        assert "archivé" in chat.last

    async def test_correcting_the_address_keeps_the_goal(self, github):
        from src.handlers.dev_hub.projects import ask_repo_again
        from src.orbi_dev.github import Lookup, RepoInfo

        github.info = RepoInfo(Lookup.NOT_FOUND)
        await admin(1)
        await service.create_integration(1, "fake", "k")
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.ask_repo_for_task, "dv:newrepo")
        await chat.say(dev_hub.on_text, "acme/fautif")
        await chat.press(ask_repo_again, "dv:repoagain")
        assert "Quel dépôt" in chat.last
        github.info = RepoInfo(Lookup.FOUND, default_branch="main")
        await chat.say(dev_hub.on_text, "acme/demo")
        await chat.press(dev_hub.confirm_repo, "dv:repook")
        assert "Que faut-il faire" in chat.last  # l'objectif « nouvelle tâche » n'a pas été perdu

    async def test_same_repo_twice_reuses_the_project(self, github):
        chat = Chat(await admin(1))
        for _ in range(2):
            await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
            await chat.say(dev_hub.on_text, "https://github.com/acme/demo")
            await chat.press(dev_hub.confirm_repo, "dv:repook")
        assert await Project.find().count() == 1
        assert "déjà dans vos projets" in chat.last

    async def test_same_name_for_another_repo_gets_the_owner_prefix(self, github):
        chat = Chat(await admin(1))
        for url in ("acme/demo", "other/demo"):
            await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
            await chat.say(dev_hub.on_text, url)
            await chat.press(dev_hub.confirm_repo, "dv:repook")
        assert {p.name for p in await Project.find().to_list()} == {"demo", "other/demo"}

    async def test_branch_in_the_url_becomes_the_project_branch(self, github):
        chat = Chat(await admin(1))
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(dev_hub.on_text, "https://github.com/acme/demo/tree/dev")
        assert "indiquée dans l'adresse" in chat.last
        await chat.press(dev_hub.confirm_repo, "dv:repook")
        assert (await Project.find_one()).default_branch == "dev"

    async def test_confirming_twice_creates_one_project(self, github):
        chat = Chat(await admin(1))
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(dev_hub.on_text, "acme/demo")
        await chat.press(dev_hub.confirm_repo, "dv:repook")
        await chat.press(dev_hub.confirm_repo, "dv:repook")
        assert await Project.find().count() == 1
        assert any("expiré" in a for a in chat.alerts)


class TestEditProject:
    async def _project(self, name="demo"):
        await admin(1)
        return await service.create_project(1, name, REPO)

    async def test_rename(self):
        project = await self._project()
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.ask_rename, f"dv:prn:{project.id}")
        assert "Nouveau nom" in chat.last
        await chat.say(dev_hub.on_text, "  Mon site \n")
        assert (await Project.get(project.id)).name == "Mon site"
        assert "Mon site" in chat.last and "Branche" in chat.last  # retour sur la fiche

    @pytest.mark.parametrize("bad", ["", "ligne un\nligne deux", "x" * 61])
    async def test_bad_names_are_refused_with_a_reason(self, bad):
        project = await self._project()
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.ask_rename, f"dv:prn:{project.id}")
        await chat.say(dev_hub.on_text, bad)
        assert (await Project.get(project.id)).name == "demo"
        assert "invalide" in chat.last or "au moins" in chat.last or "Trop court" in chat.last

    async def test_taken_name_is_refused(self):
        project = await self._project()
        await service.create_project(1, "Autre", "https://github.com/x/y")
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.ask_rename, f"dv:prn:{project.id}")
        await chat.say(dev_hub.on_text, "autre")
        assert "déjà pris" in chat.last and (await Project.get(project.id)).name == "demo"

    async def test_branch_can_be_set_and_reset(self):
        project = await self._project()
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.ask_branch, f"dv:prb:{project.id}")
        await chat.say(dev_hub.on_text, "feature/login-2")
        assert (await Project.get(project.id)).default_branch == "feature/login-2"
        await chat.press(dev_hub.ask_branch, f"dv:prb:{project.id}")
        await chat.say(dev_hub.on_text, "-")
        assert (await Project.get(project.id)).default_branch == ""
        assert "par défaut du dépôt" in chat.last

    @pytest.mark.parametrize("bad", ["avec espace", "a..b", "-x", "x/", "$(rm -rf)", "a;b", "x.lock"])
    async def test_invalid_branch_names_are_refused(self, bad):
        project = await self._project()
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.ask_branch, f"dv:prb:{project.id}")
        await chat.say(dev_hub.on_text, bad)
        assert (await Project.get(project.id)).default_branch == "" and "invalide" in chat.last

    async def test_remove_needs_confirmation_and_keeps_history(self):
        from src.handlers.dev_hub.projects import confirm_remove, remove_project

        project = await self._project()
        await service.create_integration(1, "fake", "k")
        integration = (await service.list_integrations(1))[0]
        task = await service.create_task(1, str(project.id), str(integration.id), "ancienne tâche")
        chat = Chat(await admin_user(1))
        await chat.press(confirm_remove, f"dv:prd:{project.id}")
        assert "Retirer ce projet" in chat.last and (await Project.get(project.id)).is_archived is False
        await chat.press(remove_project, f"dv:prx:{project.id}")
        assert (await Project.get(project.id)).is_archived is True
        assert await service.list_projects(1) == []
        assert (await service.get_task(1, str(task.id))).prompt == "ancienne tâche"  # l'historique reste
        # un projet retiré ne reçoit plus de travail neuf
        with pytest.raises(service.NotFoundError):
            await service.create_task(1, str(project.id), str(integration.id), "nouvelle")
        await chat.press(dev_hub.show_project, f"dv:pr:{project.id}")
        assert any("n'existe plus" in a for a in chat.alerts)

    async def test_retry_on_a_removed_project_is_refused(self):
        project = await self._project()
        await service.create_integration(1, "fake", "k")
        integration = (await service.list_integrations(1))[0]
        task = await service.create_task(1, str(project.id), str(integration.id), "x")
        ex = await service.create_execution(1, str(task.id))
        await Execution.get_pymongo_collection().update_one({"_id": ex.id}, {"$set": {"status": "failed"}})
        await service.archive_project(1, str(project.id))
        with pytest.raises(service.ConflictError):
            await service.create_execution(1, str(task.id))

    async def test_someone_elses_project_cannot_be_edited(self):
        from src.handlers.dev_hub.projects import remove_project

        foreign = await self._project()
        await admin(2)
        chat = Chat(await admin_user(2))
        for handler, data in ((dev_hub.ask_rename, f"dv:prn:{foreign.id}"), (dev_hub.ask_branch, f"dv:prb:{foreign.id}"),
                              (remove_project, f"dv:prx:{foreign.id}")):
            await chat.press(handler, data)
        assert chat.alerts.count("Ce projet n'existe plus.") == 3
        assert (await Project.get(foreign.id)).is_archived is False


class TestInputRobustness:
    async def test_photo_or_voice_gets_an_answer_not_silence(self):
        from src.handlers.dev_hub import on_unsupported

        await admin(1)
        chat = Chat(await admin_user(1))
        await chat.say(on_unsupported, "")  # hors parcours : on ne dit rien
        assert chat.shown == []
        await chat.press(dev_hub.ask_repo_from_projects, "dv:addp")
        await chat.say(on_unsupported, "")
        assert "J'attends du texte" in chat.last and "l'adresse du dépôt" in chat.last

    async def test_stale_input_is_explained(self):
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        chat.context.user_data["dev"]["at"] -= dev_hub.DRAFT_TTL + 5
        await chat.say(dev_hub.on_text, "trop tard pour cette consigne")
        assert "Saisie expirée" in chat.last
        await chat.say(dev_hub.on_text, "encore un message")  # après l'explication, plus de parcours : silence
        assert chat.shown.count(chat.last) == 1

    async def test_too_short_prompt_is_refused(self):
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        await chat.say(dev_hub.on_text, "ok")
        assert "Trop court" in chat.last
        await chat.say(dev_hub.on_text, "Corrige le bug du login")
        assert "Lancer cette tâche" in chat.last

    async def test_control_characters_are_stripped_from_a_prompt(self):
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        await chat.say(dev_hub.on_text, "Corrige\x00 le\u202e bug\n\n\n\n\ndu login")
        assert chat.context.user_data["dev"]["prompt"] == "Corrige le bug\n\ndu login"


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
        assert "↻ Actualiser" in [b.text for row in kb.inline_keyboard for b in row] if kb else False
        done = await run_with_card_status(ex, ExecutionStatus.FAILED)
        _, kb = await cards.render(done)
        labels = [b.text for row in kb.inline_keyboard for b in row] if kb else []
        assert "↻ Réessayer" not in labels and "↻ Actualiser" not in labels

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


def styles(chat: Chat) -> dict[str, str | None]:
    return {b.text: b.api_kwargs.get("style") or getattr(b, "style", None)
            for row in chat.markups[-1].inline_keyboard for b in row}


class TestLook:
    """Un seul bouton coloré par écran : celui qu'on attend de l'utilisateur."""

    async def test_home_has_one_primary_button(self):
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.show_home, "dv:home")
        colored = {t: s for t, s in styles(chat).items() if s}
        assert colored == {"+ Nouvelle tâche": "primary"}

    async def test_launch_is_green_and_cancel_is_neutral(self):
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        await chat.say(dev_hub.on_text, "Fais ceci")
        colored = {t: s for t, s in styles(chat).items() if s}
        assert colored == {"Lancer": "success"}

    async def test_instruction_is_quoted_and_long_ones_fold(self):
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.start_task, "dv:new")
        await chat.say(dev_hub.on_text, "court")
        assert "<blockquote>court</blockquote>" in chat.last
        await chat.press(dev_hub.edit_prompt, "dv:edit")
        await chat.say(dev_hub.on_text, "long " * 80)
        assert "<blockquote expandable>" in chat.last

    async def test_card_shows_progress_and_quotes_the_instruction(self):
        await admin(1)
        ex = await run_with_card(ExecutionStatus.QUEUED)
        for status, bar in ((ExecutionStatus.QUEUED, "▰▱▱"), (ExecutionStatus.RUNNING, "▰▰▱"),
                            (ExecutionStatus.SUCCEEDED, "▰▰▰"), (ExecutionStatus.FAILED, "▰▰✕")):
            ex = await run_with_card_status(ex, status)
            text, _ = await cards.render(ex)
            assert bar in text and "<blockquote>Ajoute un test</blockquote>" in text

    async def test_retry_is_the_only_colored_button_of_an_alert(self):
        from src.orbi_dev import notifier

        await admin(1)
        ex = await run_with_card(ExecutionStatus.FAILED)
        keyboard = notifier.build_keyboard(ex)
        colored = {b.text: getattr(b, "style", None) for row in keyboard.inline_keyboard for b in row if getattr(b, "style", None)}
        assert colored == {"↻ Réessayer": "primary"}

    async def test_admin_gets_a_command_menu_on_start(self):
        await setup_workspace(1)
        chat = Chat(await admin_user(1))
        await chat.say(dev_hub.show_home, "/start")
        sent = chat.context.bot.set_my_commands.await_args
        assert [c.command for c in sent.args[0]] == ["start", "task", "tasks", "web"]
        assert sent.kwargs["scope"].chat_id == 1
        chat.context.bot.set_my_commands.reset_mock()
        await chat.press(dev_hub.show_home, "dv:home")  # un simple bouton ne rappelle pas Telegram
        chat.context.bot.set_my_commands.assert_not_awaited()


def emojis_in(text: str) -> list[str]:
    """Les emoji (plans étendus, sélecteur de variation, dingbats colorés) ; ✓ et ✕ sont des symboles de texte."""
    return [
        c for c in text
        if ord(c) >= 0x1F000 or c == "\ufe0f" or 0x23E9 <= ord(c) <= 0x23FA or ord(c) in (0x2B50, 0x2B55)
        or (0x2600 <= ord(c) <= 0x27BF and c not in "✓✕")
    ]


def all_text(chat: Chat) -> str:
    return "\n".join(chat.shown) + "\n".join(
        b.text for markup in chat.markups if markup for row in markup.inline_keyboard for b in row
    )


class TestStructure:
    """Chaque écran a une issue, parle sans emoji et ne montre que les données de son propriétaire."""

    async def _seed(self):
        await admin(1)
        await setup_workspace(1)
        projects, integration = await service.list_projects(1), (await service.list_integrations(1))[0]
        runs = []
        for status in (ExecutionStatus.RUNNING, ExecutionStatus.NEEDS_ATTENTION, ExecutionStatus.SUCCEEDED,
                       ExecutionStatus.FAILED):
            task = await service.create_task(1, str(projects[0].id), str(integration.id), f"tâche {status.value}")
            ex = await service.create_execution(1, str(task.id))
            await Execution.get_pymongo_collection().update_one({"_id": ex.id}, {"$set": {"status": status.value}})
            runs.append(await Execution.get(ex.id))
        return projects[0], runs

    async def test_no_emoji_anywhere_and_every_screen_has_a_way_back(self):
        project, runs = await self._seed()
        chat = Chat(await admin_user(1))
        screens = [
            (dev_hub.show_home, "dv:home"), (dev_hub.show_list, "dv:list"), (dev_hub.show_list, "dv:list:d"),
            (dev_hub.show_projects, "dv:projects"), (dev_hub.show_project, f"dv:pr:{project.id}"),
            (dev_hub.show_connections, "dv:conn"), (dev_hub.show_settings, "dv:set"),
            (dev_hub.show_execution, f"dv:e:{runs[0].id}"), (dev_hub.start_task, "dv:new"),
        ]
        for handler, data in screens:
            await chat.press(handler, data)
            assert not emojis_in(all_text(chat)), f"emoji dans {data}"
            if data != "dv:home":
                assert any(b.text.startswith("‹") or b.text == "Annuler" for row in chat.markups[-1].inline_keyboard for b in row), data
        await chat.say(dev_hub.on_text, "Fais ceci")
        assert not emojis_in(all_text(chat))

    async def test_list_has_two_tabs_with_counts_and_filters(self):
        _, runs = await self._seed()
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.show_list, "dv:list")  # des tâches en cours : l'onglet « En cours » s'ouvre
        assert chat.last_buttons()[:2] == ["● En cours 2", "Terminées 2"]
        assert any("tâche running" in b for b in chat.last_buttons()) and not any("succeeded" in b for b in chat.last_buttons())
        await chat.press(dev_hub.show_list, "dv:list:d")
        assert chat.last_buttons()[:2] == ["En cours 2", "● Terminées 2"]
        assert any("tâche succeeded" in b for b in chat.last_buttons()) and not any("running" in b for b in chat.last_buttons())

    async def test_list_opens_on_finished_when_nothing_is_running(self):
        await admin(1)
        await setup_workspace(1)
        project, integration = (await service.list_projects(1))[0], (await service.list_integrations(1))[0]
        task = await service.create_task(1, str(project.id), str(integration.id), "vieille tâche")
        ex = await service.create_execution(1, str(task.id))
        await Execution.get_pymongo_collection().update_one({"_id": ex.id}, {"$set": {"status": "succeeded"}})
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.show_list, "dv:list")
        assert chat.last_buttons()[1] == "● Terminées 1"

    async def test_project_sheet_and_new_task_from_it(self):
        project, _ = await self._seed()
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.show_project, f"dv:pr:{project.id}")
        assert "demo0" in chat.last and "par défaut du dépôt" in chat.last and "<b>4</b>" in chat.last
        await chat.press(dev_hub.new_task_in_project, f"dv:pn:{project.id}")
        assert "Que faut-il faire sur demo0" in chat.last

    async def test_someone_elses_project_sheet_is_refused(self):
        await admin(2)
        await service.create_project(2, "autre", "https://github.com/x/y")
        foreign = (await service.list_projects(2))[0]
        await admin(1)
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.show_project, f"dv:pr:{foreign.id}")
        await chat.press(dev_hub.new_task_in_project, f"dv:pn:{foreign.id}")
        assert chat.alerts.count("Ce projet n'existe plus.") == 2

    async def test_connections_lists_providers_without_any_secret(self):
        await admin(1)
        await service.create_integration(1, "fake", "super-secret-key-123", label="agent-perso")
        chat = Chat(await admin_user(1))
        await chat.press(dev_hub.show_connections, "dv:conn")
        assert "agent-perso" in chat.last and "Actif" in chat.last
        assert "super-secret-key-123" not in all_text(chat)
        assert "/web" in chat.last  # sans https public, on explique comment ouvrir la page web

    async def test_alerts_can_be_switched_off_and_on(self):
        user = await admin(1)
        chat = Chat(user)
        await chat.press(dev_hub.show_settings, "dv:set")
        assert "activées" in chat.last and "Désactiver les alertes" in chat.last_buttons()
        await chat.press(dev_hub.toggle_notifications, "dv:notif")
        assert "désactivées" in chat.last
        assert "dev_runs" not in (await User.get(user.id)).enabled_notifications
        await chat.press(dev_hub.toggle_notifications, "dv:notif")
        assert "dev_runs" in (await User.get(user.id)).enabled_notifications

    async def test_other_modules_are_reachable_from_settings(self):
        chat = Chat(await admin(1))
        await chat.press(dev_hub.show_settings, "dv:set")
        assert "nav:more" in chat.last_data()

    async def test_quiet_and_empty_homes_have_no_emoji_either(self):
        chat = Chat(await admin(1))
        await chat.press(dev_hub.show_home, "dv:home")  # compte vide : « pour commencer »
        assert "○" in chat.last and not emojis_in(all_text(chat))
        await setup_workspace(1)
        await chat.press(dev_hub.show_home, "dv:home")  # prêt, aucune tâche
        assert "Rien en cours." in chat.last and not emojis_in(all_text(chat))
        project, integration = (await service.list_projects(1))[0], (await service.list_integrations(1))[0]
        task = await service.create_task(1, str(project.id), str(integration.id), "faite")
        ex = await service.create_execution(1, str(task.id))
        await Execution.get_pymongo_collection().update_one({"_id": ex.id}, {"$set": {"status": "succeeded"}})
        await chat.press(dev_hub.show_home, "dv:home")  # tâches terminées seulement
        assert "Rien en cours." in chat.last and "✓" in chat.last and not emojis_in(all_text(chat))
