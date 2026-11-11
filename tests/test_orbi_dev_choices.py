"""Choix cliquables de l'agent (ADR-0010) : parsing des options et boutons proposés."""

import pytest
from cryptography.fernet import Fernet

from src.core.config import get_settings
from src.orbi_dev import runner, service
from src.orbi_dev.choices import (
    CB_GEN,
    CB_OPT,
    GENERIC_CHOICES,
    agent_choice_buttons,
    option_fingerprint,
    parse_options,
)
from src.orbi_dev.connectors.fake import FakeConnector
from src.orbi_dev.state import ExecutionStatus

REPO = "https://github.com/acme/demo"


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    FakeConnector.reset()
    yield
    FakeConnector.reset()


class TestParseOptions:
    def test_numbered_options_in_a_question(self):
        text = "Quelle approche préfères-tu ?\n\n1) Garder la structure\n2) Réécrire le module\n3) Attendre"
        assert parse_options(text) == ["Garder la structure", "Réécrire le module", "Attendre"]

    def test_bulleted_options(self):
        text = "Tu préfères quoi ?\n- Option rapide\n- Option soignée"
        assert parse_options(text) == ["Option rapide", "Option soignée"]

    def test_markdown_emphasis_is_stripped(self):
        text = "Choisis ?\n1) **Option A**\n2) `Option B`"
        assert parse_options(text) == ["Option A", "Option B"]

    def test_no_question_mark_means_no_options(self):
        # Une liste d'étapes n'est pas une question à choix.
        assert parse_options("Étapes :\n1) Faire ci\n2) Faire ça") == []

    def test_single_item_is_not_a_choice(self):
        assert parse_options("Une seule option ?\n1) Unique") == []

    def test_capped_at_four(self):
        text = "Lequel ?\n" + "\n".join(f"{i}) Choix {i}" for i in range(1, 8))
        assert parse_options(text) == [f"Choix {i}" for i in range(1, 5)]

    def test_overlong_items_are_skipped(self):
        text = "Lequel ?\n1) " + "x" * 300 + "\n2) Court\n3) Autre"
        assert parse_options(text) == ["Court", "Autre"]

async def _waiting(owner: int, prompt: str):
    FakeConnector.reset()
    project = await service.create_project(owner, "demo", REPO)
    integration = await runner.connect_integration(owner, "fake", "secret-key")
    task = await service.create_task(owner, str(project.id), str(integration.id), prompt)
    execution = await service.create_execution(owner, str(task.id))
    await runner.launch_execution(owner, str(execution.id))
    await runner.refresh_execution(owner, str(execution.id))
    await runner.refresh_execution(owner, str(execution.id))
    return await service.get_execution(owner, str(execution.id))

class TestAgentChoiceButtons:
    async def test_parsed_options_become_buttons(self):
        execution = await _waiting(9300, "quelle approche ? [askopts]")
        assert execution.status == ExecutionStatus.NEEDS_ATTENTION
        buttons = await agent_choice_buttons(9300, execution)
        labels = [b.text for b in buttons]
        assert labels == ["Garder la structure actuelle", "Réécrire le module", "Attendre mon avis"]
        for b in buttons:
            assert b.callback_data.startswith(CB_OPT)
            assert len(b.callback_data) <= 64  # limite Telegram

    async def test_generic_fallback_without_readable_options(self):
        execution = await _waiting(9301, "question [ask]")  # question sans liste
        buttons = await agent_choice_buttons(9301, execution)
        assert [b.text for b in buttons] == GENERIC_CHOICES
        assert all(b.callback_data.startswith(CB_GEN) for b in buttons)

    async def test_no_buttons_while_running_or_finished(self):
        FakeConnector.reset()
        project = await service.create_project(9302, "demo", REPO)
        integration = await runner.connect_integration(9302, "fake", "k")
        task = await service.create_task(9302, str(project.id), str(integration.id), "travail")
        execution = await service.create_execution(9302, str(task.id))
        await runner.launch_execution(9302, str(execution.id))
        running = await service.get_execution(9302, str(execution.id))
        assert await agent_choice_buttons(9302, running) == []
        # terminée : plus de choix non plus
        for _ in range(3):
            await runner.refresh_execution(9302, str(execution.id))
        done = await service.get_execution(9302, str(execution.id))
        assert await agent_choice_buttons(9302, done) == []

    async def test_no_buttons_without_an_external_session(self):
        FakeConnector.reset()
        project = await service.create_project(9303, "demo", REPO)
        integration = await runner.connect_integration(9303, "fake", "k")
        task = await service.create_task(9303, str(project.id), str(integration.id), "question [ask]")
        execution = await service.create_execution(9303, str(task.id))  # queued : pas encore lancée
        assert await agent_choice_buttons(9303, execution) == []

    async def test_fingerprint_detects_a_changed_option(self):
        assert option_fingerprint("Réécrire le module") == option_fingerprint("Réécrire le module")
        assert option_fingerprint("a") != option_fingerprint("b")
