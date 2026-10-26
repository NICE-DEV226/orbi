"""Tests de l'interface mobile Orbi Dev : accès, isolation, CSRF, XSS, parcours complet."""

import httpx
import pytest
from cryptography.fernet import Fernet

from src.core.config import get_settings
from src.main import create_app
from src.models.user import User
from src.orbi_dev import runner, service
from src.orbi_dev.connectors.base import RemoteRun, RemoteStatus
from src.orbi_dev.connectors.fake import FakeConnector
from src.web.auth import COOKIE_NAME, create_web_session
from src.web.csrf import csrf_token

API_KEY = "key_super_secret_value_123456"
REPO = "https://github.com/acme/demo"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    FakeConnector.reset()
    yield
    FakeConnector.reset()


async def login(role="admin", telegram_id=500) -> tuple[httpx.AsyncClient, User, str]:
    user = await User(telegram_id=telegram_id, first_name="Dev", role=role).insert()
    session_id = await create_web_session(user)
    transport = httpx.ASGITransport(app=create_app())
    client = httpx.AsyncClient(transport=transport, base_url="http://test", cookies={COOKIE_NAME: session_id})
    return client, user, csrf_token(session_id)


async def seed(owner: int, prompt="Corrige le bug"):
    project = await service.create_project(owner, "demo", REPO)
    integration = await runner.connect_integration(owner, "fake", API_KEY)
    task = await service.create_task(owner, str(project.id), str(integration.id), prompt)
    execution = await service.create_execution(owner, str(task.id))
    return project, integration, task, execution


class TestAccess:
    @pytest.mark.parametrize("path", ["/dev/", "/dev/runs", "/dev/tasks/new", "/dev/projects", "/dev/integrations",
                                      "/dev/executions/abc", "/dev/executions/abc/panel"])
    async def test_anonymous_is_redirected_to_login(self, path):
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(path)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/login")

    async def test_non_admin_session_is_refused(self):
        client, _, _ = await login(role="user")
        async with client:
            assert (await client.get("/dev/")).status_code == 303

    async def test_pages_are_mobile_ready(self):
        client, _, _ = await login()
        async with client:
            html = (await client.get("/dev/")).text
        assert 'name="viewport"' in html and "width=device-width" in html
        assert 'class="tabbar"' in html


class TestIsolation:
    async def test_user_sees_only_their_own_tasks_and_executions(self):
        alice, _, _ = await login(telegram_id=501)
        bob, _, _ = await login(telegram_id=502)
        _, _, _, execution = await seed(501, prompt="Tâche secrète pour Alice")
        async with alice, bob:
            assert "Tâche secrète pour Alice" in (await alice.get("/dev/")).text
            assert "Tâche secrète pour Alice" not in (await bob.get("/dev/")).text
            assert (await bob.get(f"/dev/executions/{execution.id}")).status_code == 404
            assert (await bob.get(f"/dev/api/executions/{execution.id}")).status_code == 404

    async def test_other_user_cannot_cancel_or_refresh(self):
        _, _, bob_token = await login(telegram_id=502)
        _, _, _, execution = await seed(501)
        bob, _, token = await login(telegram_id=503)
        async with bob:
            for action in ("cancel", "refresh"):
                r = await bob.post(f"/dev/executions/{execution.id}/{action}", data={"csrf_token": token})
                assert r.status_code == 404


class TestCsrf:
    @pytest.mark.parametrize("path", ["/dev/projects", "/dev/integrations", "/dev/tasks",
                                      "/dev/executions/abc/cancel", "/dev/executions/abc/refresh",
                                      "/dev/tasks/abc/retry", "/dev/integrations/abc/revoke"])
    async def test_post_without_token_is_forbidden(self, path):
        client, _, _ = await login()
        async with client:
            assert (await client.post(path, data={})).status_code == 403

    async def test_wrong_token_is_forbidden(self):
        client, _, _ = await login()
        async with client:
            r = await client.post("/dev/projects", data={"csrf_token": "x" * 64, "name": "p", "repo_url": REPO})
        assert r.status_code == 403
        assert await service.list_projects(500) == []

    async def test_token_from_another_session_is_forbidden(self):
        client, _, _ = await login(telegram_id=504)
        _, _, other_token = await login(telegram_id=505)
        async with client:
            r = await client.post("/dev/projects", data={"csrf_token": other_token, "name": "p", "repo_url": REPO})
        assert r.status_code == 403

    async def test_get_requests_never_change_state(self):
        client, _, _ = await login()
        _, _, _, execution = await seed(500)
        async with client:
            for path in (f"/dev/executions/{execution.id}/cancel", f"/dev/executions/{execution.id}/refresh"):
                assert (await client.get(path)).status_code == 405


class TestFullJourney:
    async def test_project_key_task_to_pull_request(self):
        client, _, token = await login()
        async with client:
            r = await client.post("/dev/projects", data={"csrf_token": token, "name": "demo", "repo_url": REPO})
            assert r.status_code == 303
            r = await client.post("/dev/integrations", data={"csrf_token": token, "provider": "fake", "api_key": API_KEY})
            assert r.status_code == 303

            project = (await service.list_projects(500))[0]
            integration = (await service.list_integrations(500))[0]
            r = await client.post("/dev/tasks", data={
                "csrf_token": token, "project_id": str(project.id), "integration_id": str(integration.id),
                "prompt": "Ajoute un README"})
            assert r.status_code == 303
            page_url = r.headers["location"]
            execution_id = page_url.rsplit("/", 1)[1]

            # Le lancement tourne en tâche de fond ; on laisse l'orchestrateur terminer le travail.
            await runner.refresh_active_executions()
            await client.post(f"/dev/executions/{execution_id}/refresh", data={"csrf_token": token})
            await client.post(f"/dev/executions/{execution_id}/refresh", data={"csrf_token": token})

            page = await client.get(page_url)
            assert "Terminé" in page.text and "Une pull request est prête" in page.text
            assert 'href="https://github.com/acme/demo/pull/1"' in page.text
            assert "hx-trigger" not in page.text.split('id="run-panel"')[1].split(">")[0]  # terminé : le suivi s'arrête
            # rechargement : l'état vient de la base, identique
            assert "Une pull request est prête" in (await client.get(page_url)).text

    async def test_cancel_from_the_ui(self):
        client, _, token = await login()
        _, _, _, execution = await seed(500)
        await runner.launch_execution(500, str(execution.id))
        async with client:
            r = await client.post(f"/dev/executions/{execution.id}/cancel", data={"csrf_token": token})
            assert r.status_code == 303
        assert (await service.get_execution(500, str(execution.id))).status.value == "cancelled"

    async def test_retry_only_after_a_terminal_execution(self):
        client, _, token = await login()
        _, _, task, execution = await seed(500)
        async with client:
            await client.post(f"/dev/tasks/{task.id}/retry", data={"csrf_token": token})
            assert len(await service.list_executions(500, task_id=str(task.id))) == 1  # refusé : déjà active
            await runner.request_cancel(500, str(execution.id))
            r = await client.post(f"/dev/tasks/{task.id}/retry", data={"csrf_token": token})
            assert r.status_code == 303
        assert len(await service.list_executions(500, task_id=str(task.id))) == 2

    async def test_active_page_polls_and_terminal_page_does_not(self):
        client, _, _ = await login()
        _, _, _, execution = await seed(500)
        async with client:
            active = (await client.get(f"/dev/executions/{execution.id}")).text
            await runner.request_cancel(500, str(execution.id))
            done = (await client.get(f"/dev/executions/{execution.id}")).text
        assert 'hx-trigger="every 3s"' in active and "Arrêter" in active
        assert 'hx-trigger="every 3s"' not in done and "Nouvelle tentative" in done


class TestIntegrationsSafety:
    async def test_invalid_key_is_rejected_with_a_message_and_nothing_stored(self):
        client, _, token = await login()
        async with client:
            r = await client.post("/dev/integrations", data={"csrf_token": token, "provider": "fake", "api_key": "invalid"})
        assert r.status_code == 200
        assert "refusé cette clé" in r.text
        assert await service.list_integrations(500) == []

    async def test_api_key_never_appears_in_any_page(self):
        client, _, token = await login()
        async with client:
            await client.post("/dev/integrations", data={"csrf_token": token, "provider": "fake", "api_key": API_KEY})
            for path in ("/dev/", "/dev/integrations", "/dev/projects", "/dev/tasks/new"):
                assert API_KEY not in (await client.get(path)).text
            assert API_KEY not in (await client.post(
                "/dev/integrations", data={"csrf_token": token, "provider": "nope", "api_key": API_KEY})).text

    async def test_missing_encryption_key_gives_a_clear_message(self, monkeypatch):
        monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "")
        get_settings.cache_clear()
        client, _, token = await login()
        async with client:
            r = await client.post("/dev/integrations", data={"csrf_token": token, "provider": "fake", "api_key": API_KEY})
        assert "chiffrement" in r.text
        assert API_KEY not in r.text

    async def test_revoke_from_the_ui(self):
        client, _, token = await login()
        _, integration, _, _ = await seed(500)
        async with client:
            r = await client.post(f"/dev/integrations/{integration.id}/revoke", data={"csrf_token": token})
            assert r.status_code == 303
            assert "Révoquée" in (await client.get("/dev/integrations")).text

    async def test_fake_provider_is_not_offered_in_production(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("JWT_SECRET", "x" * 40)
        get_settings.cache_clear()
        client, _, _ = await login()
        async with client:
            html = (await client.get("/dev/integrations")).text
        assert '<option value="fake">' not in html
        assert '<option value="cursor">' in html


class TestUntrustedContent:
    async def _execution_with_remote(self, monkeypatch, **remote_fields):
        _, _, _, execution = await seed(500)

        async def hostile_get(self, external_id):
            return RemoteRun(RemoteStatus.SUCCEEDED, external_id, **remote_fields)

        monkeypatch.setattr(FakeConnector, "get", hostile_get)
        await runner.launch_execution(500, str(execution.id))
        await runner.refresh_execution(500, str(execution.id))
        return execution

    async def test_provider_text_is_escaped(self, monkeypatch):
        execution = await self._execution_with_remote(
            monkeypatch, summary="<script>alert(1)</script>", branch="<img src=x onerror=alert(2)>")
        client, _, _ = await login()
        async with client:
            html = (await client.get(f"/dev/executions/{execution.id}")).text
        assert "<script>alert(1)</script>" not in html
        assert "<img src=x" not in html
        assert "&lt;script&gt;" in html

    @pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,<b>x</b>", "http://insecure.example/pr/1"])
    async def test_non_https_links_are_never_rendered(self, monkeypatch, url):
        execution = await self._execution_with_remote(monkeypatch, pr_url=url, external_url=url)
        client, _, _ = await login()
        async with client:
            html = (await client.get(f"/dev/executions/{execution.id}")).text
            fragment = (await client.get(f"/dev/executions/{execution.id}/panel")).text
        assert url not in html and url not in fragment
        assert "Ouvrir la pull request" not in html

    async def test_user_prompt_is_escaped(self):
        client, _, _ = await login()
        _, _, _, execution = await seed(500, prompt='"><script>alert(3)</script>')
        async with client:
            html = (await client.get(f"/dev/executions/{execution.id}")).text
        assert "<script>alert(3)</script>" not in html

    async def test_authenticated_pages_and_fragments_are_not_cacheable(self):
        client, _, _ = await login()
        _, _, _, execution = await seed(500)
        async with client:
            for path in ("/dev/", "/dev/runs", f"/dev/executions/{execution.id}", f"/dev/executions/{execution.id}/panel"):
                assert (await client.get(path)).headers["cache-control"] == "no-store", path
