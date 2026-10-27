"""Connecteur Jules (API v1alpha) : traduction des réponses, lancement sans identifiant client, réconciliation."""

import json

import httpx
import pytest
from cryptography.fernet import Fernet

from src.core.config import get_settings
from src.orbi_dev import runner, service
from src.orbi_dev.connectors import registry
from src.orbi_dev.connectors.base import Capability, ConnectorError, ErrorCategory, LaunchRequest, RemoteStatus
from src.orbi_dev.connectors.jules import JulesConnector
from src.orbi_dev.models import EventKind
from src.orbi_dev.state import ExecutionStatus as S

API_KEY = "AIzaSyJULES_super_secret_key_1234567890"
REF = "00000000-0000-0000-0000-000000000001"
REQUEST = LaunchRequest(REF, "Ajoute un README\navec des exemples", "https://github.com/Acme/Demo", "main")
ALICE = 1001


class FakeJules:
    """Serveur Jules minimal et à état, branché sur httpx.MockTransport."""

    def __init__(self):
        self.sources = [{
            "name": "sources/github/acme/demo",
            "githubRepo": {
                "owner": "acme", "repo": "demo", "isPrivate": False,
                "defaultBranch": {"displayName": "main"},
                "branches": [{"displayName": "main"}, {"displayName": "develop"}],
            },
        }]
        self.sessions: dict[str, dict] = {}
        self.activities: dict[str, list[dict]] = {}
        self.requests: list[httpx.Request] = []
        self.lose_next_create = False
        self.fail_activities = False
        self.source_pages: list[list[dict]] | None = None
        self.session_pages: list[list[dict]] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        params = dict(request.url.params)
        if request.headers.get("x-goog-api-key") != API_KEY:
            return httpx.Response(400, json={"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                                       "message": "API key not valid. Please pass a valid API key.",
                                                       "details": [{"reason": "API_KEY_INVALID"}]}})
        if path == "/v1alpha/sources":
            if self.source_pages is not None:
                index = int(params.get("pageToken", 0))
                body = {"sources": self.source_pages[index]}
                if index + 1 < len(self.source_pages):
                    body["nextPageToken"] = str(index + 1)
                return httpx.Response(200, json=body)
            return httpx.Response(200, json={"sources": self.sources})
        if path == "/v1alpha/sessions" and method == "POST":
            body = json.loads(request.content)
            session_id = f"s{len(self.sessions) + 1}"
            self.sessions[session_id] = {
                "name": f"sessions/{session_id}", "id": session_id, "prompt": body["prompt"], "title": body["title"],
                "state": "QUEUED", "url": f"https://jules.google.com/session/{session_id}", "outputs": [],
            }
            if self.lose_next_create:
                self.lose_next_create = False
                raise httpx.ReadTimeout("réponse perdue")
            return httpx.Response(200, json=self.sessions[session_id])
        if path == "/v1alpha/sessions" and method == "GET":
            if self.session_pages is not None:
                index = int(params.get("pageToken", 0))
                body = {"sessions": self.session_pages[index]}
                if index + 1 < len(self.session_pages):
                    body["nextPageToken"] = str(index + 1)
                return httpx.Response(200, json=body)
            return httpx.Response(200, json={"sessions": list(self.sessions.values())})
        if path.endswith("/activities"):
            if self.fail_activities:
                return httpx.Response(503, json={"error": {"status": "UNAVAILABLE", "message": "down"}})
            session_id = path.split("/")[3]
            return httpx.Response(200, json={"activities": self.activities.get(session_id, [])})
        if path.startswith("/v1alpha/sessions/") and method == "GET":
            session = self.sessions.get(path.rsplit("/", 1)[1])
            if session is None:
                return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "message": "no such session"}})
            return httpx.Response(200, json=session)
        return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "message": path}})


async def no_sleep(_: float) -> None:
    return None


def connector(server: FakeJules, key: str = API_KEY) -> JulesConnector:
    return JulesConnector(key, transport=httpx.MockTransport(server), sleep=no_sleep)


def finish(server: FakeJules, session_id: str, state: str, **extra) -> None:
    server.sessions[session_id].update(state=state, **extra)


class TestVerifyAndErrors:
    async def test_verify_is_a_read_only_call_with_the_key_in_a_header(self):
        server = FakeJules()
        result = await connector(server).verify()
        request = server.requests[0]
        assert request.method == "GET" and request.url.path == "/v1alpha/sources"
        assert request.headers["x-goog-api-key"] == API_KEY and API_KEY not in str(request.url)
        assert Capability.LAUNCH in result.capabilities and Capability.CANCEL not in result.capabilities

    async def test_google_reports_a_bad_key_as_400_and_it_is_still_an_auth_error(self):
        with pytest.raises(ConnectorError) as exc:
            await connector(FakeJules(), key="wrong").verify()
        assert exc.value.category == ErrorCategory.AUTH_INVALID and not exc.value.retryable
        assert "wrong" not in exc.value.message

    @pytest.mark.parametrize("body", [
        {"error": {"status": "INVALID_ARGUMENT", "message": "API key not valid. Please pass a valid API key."}},
        {"error": {"status": "INVALID_ARGUMENT", "message": "x", "details": [{"reason": "API_KEY_INVALID"}]}},
    ])
    async def test_bad_key_is_recognised_by_message_or_by_reason(self, body):
        from src.orbi_dev.connectors.jules import error_from_response

        assert error_from_response(httpx.Response(400, json=body)).category == ErrorCategory.AUTH_INVALID

    @pytest.mark.parametrize("status,body,category,retryable", [
        (401, {"error": {"status": "UNAUTHENTICATED", "message": "x"}}, ErrorCategory.AUTH_INVALID, False),
        (403, {"error": {"status": "PERMISSION_DENIED", "message": "x"}}, ErrorCategory.PERMISSION_DENIED, False),
        (429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}}, ErrorCategory.PLAN_OR_QUOTA, False),
        (503, {"error": {"status": "UNAVAILABLE", "message": "x"}}, ErrorCategory.UNAVAILABLE, True),
        (500, "not json", ErrorCategory.UNAVAILABLE, True),
        (418, {}, ErrorCategory.UNKNOWN, False),
    ])
    async def test_error_translation(self, status, body, category, retryable):
        from src.orbi_dev.connectors.jules import error_from_response

        error = error_from_response(httpx.Response(status, json=body) if isinstance(body, dict) else httpx.Response(status, text=body))
        assert error.category == category and error.retryable == retryable

    async def test_rate_limit_with_a_wait_is_retryable(self):
        from src.orbi_dev.connectors.jules import error_from_response

        error = error_from_response(httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"status": "RESOURCE_EXHAUSTED"}}))
        assert error.category == ErrorCategory.RATE_LIMITED and error.retryable and error.retry_after == 7.0

    async def test_transient_errors_are_retried_a_bounded_number_of_times(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE", "message": "x"}})

        c = JulesConnector(API_KEY, transport=httpx.MockTransport(handler), sleep=no_sleep, max_retries=2)
        with pytest.raises(ConnectorError):
            await c.verify()
        assert len(calls) == 3


class TestLaunch:
    async def test_request_shape(self):
        server = FakeJules()
        remote = await connector(server).launch(REQUEST)

        create = [r for r in server.requests if r.method == "POST"][0]
        body = json.loads(create.content)
        assert body["prompt"] == REQUEST.prompt
        assert body["sourceContext"] == {"source": "sources/github/acme/demo", "githubRepoContext": {"startingBranch": "main"}}
        assert body["automationMode"] == "AUTO_CREATE_PR"
        assert f"[orbi:{REF}]" in body["title"] and body["title"].startswith("Ajoute un README ")
        assert remote.status == RemoteStatus.PENDING and remote.external_id == "s1"
        assert remote.external_url == "https://jules.google.com/session/s1"

    async def test_repository_is_found_on_a_later_page_ignoring_case_and_dot_git(self):
        server = FakeJules()
        server.source_pages = [[{"name": "sources/github/x/y", "githubRepo": {"owner": "x", "repo": "y"}}],
                               [{"name": "sources/github/acme/demo", "githubRepo": {"owner": "ACME", "repo": "Demo"}}]]
        await connector(server).launch(LaunchRequest(REF, "p", "https://github.com/acme/demo.git", "main"))
        assert any(r.method == "POST" for r in server.requests)

    async def test_repository_not_connected_to_jules_is_a_clear_permission_error(self):
        server = FakeJules()
        with pytest.raises(ConnectorError) as exc:
            await connector(server).launch(LaunchRequest(REF, "p", "https://github.com/acme/other", "main"))
        assert exc.value.category == ErrorCategory.PERMISSION_DENIED and exc.value.code == "repository_access"
        assert "acme/other" in exc.value.message and not any(r.method == "POST" for r in server.requests)

    async def test_empty_branch_means_the_repositorys_default_branch(self):
        server = FakeJules()
        server.sources[0]["githubRepo"]["defaultBranch"] = {"displayName": "master"}
        server.sources[0]["githubRepo"]["branches"] = [{"displayName": "master"}]
        await connector(server).launch(LaunchRequest(REF, "p", "https://github.com/acme/demo", ""))
        body = json.loads([r for r in server.requests if r.method == "POST"][0].content)
        assert body["sourceContext"]["githubRepoContext"]["startingBranch"] == "master"

    async def test_unknown_branch_is_refused_before_any_session_is_created(self):
        """Une branche inexistante fait échouer Jules au clonage : on l'évite et on dit quelles branches existent."""
        server = FakeJules()
        server.sources[0]["githubRepo"]["defaultBranch"] = {"displayName": "master"}
        server.sources[0]["githubRepo"]["branches"] = [{"displayName": "master"}, {"displayName": "dev"}]
        with pytest.raises(ConnectorError) as exc:
            await connector(server).launch(LaunchRequest(REF, "p", "https://github.com/acme/demo", "main"))
        assert exc.value.category == ErrorCategory.INVALID_REQUEST and exc.value.code == "branch_not_found"
        assert "« main »" in exc.value.message and "« master »" in exc.value.message and "« dev »" in exc.value.message
        assert not any(r.method == "POST" for r in server.requests)

    async def test_branch_is_accepted_when_jules_does_not_list_branches(self):
        server = FakeJules()
        server.sources[0]["githubRepo"].pop("branches")
        await connector(server).launch(LaunchRequest(REF, "p", "https://github.com/acme/demo", "feature/x"))
        body = json.loads([r for r in server.requests if r.method == "POST"][0].content)
        assert body["sourceContext"]["githubRepoContext"]["startingBranch"] == "feature/x"

    async def test_empty_branch_without_a_known_default_asks_for_one(self):
        server = FakeJules()
        server.sources[0]["githubRepo"].pop("defaultBranch")
        with pytest.raises(ConnectorError) as exc:
            await connector(server).launch(LaunchRequest(REF, "p", "https://github.com/acme/demo", ""))
        assert exc.value.code == "branch_required" and not any(r.method == "POST" for r in server.requests)

    @pytest.mark.parametrize("url", ["https://gitlab.com/acme/demo", "https://github.com/acme", "https://github.com/a/b/c", "http://github.com/a/b"])
    async def test_only_github_repositories_are_supported(self, url):
        with pytest.raises(ConnectorError) as exc:
            await connector(FakeJules()).launch(LaunchRequest(REF, "p", url, "main"))
        assert exc.value.category == ErrorCategory.INVALID_REQUEST

    async def test_a_lost_response_is_never_retried_blindly(self):
        server = FakeJules()
        server.lose_next_create = True
        with pytest.raises(ConnectorError) as exc:
            await connector(server).launch(REQUEST)
        assert exc.value.outcome_unknown
        assert len([r for r in server.requests if r.method == "POST"]) == 1  # un seul POST : pas de doublon

    async def test_the_lost_session_is_found_by_its_reference(self):
        server = FakeJules()
        server.lose_next_create = True
        c = connector(server)
        with pytest.raises(ConnectorError):
            await c.launch(REQUEST)
        remote = await c.find_by_client_ref(REF)
        assert remote is not None and remote.external_id == "s1"
        assert await c.find_by_client_ref("another-ref") is None

    async def test_lookup_scans_several_pages_and_never_creates(self):
        server = FakeJules()
        other = {"id": "o", "title": "autre [orbi:zzz]", "state": "QUEUED"}
        mine = {"id": "m", "title": f"x [orbi:{REF}]", "state": "IN_PROGRESS"}
        server.session_pages = [[other], [mine]]
        remote = await connector(server).find_by_client_ref(REF)
        assert remote.external_id == "m" and remote.status == RemoteStatus.RUNNING
        assert all(r.method == "GET" for r in server.requests)


class TestStateMapping:
    @pytest.mark.parametrize("state,status", [
        ("QUEUED", RemoteStatus.PENDING), ("PLANNING", RemoteStatus.RUNNING), ("IN_PROGRESS", RemoteStatus.RUNNING),
        ("AWAITING_PLAN_APPROVAL", RemoteStatus.WAITING), ("AWAITING_USER_FEEDBACK", RemoteStatus.WAITING),
        ("PAUSED", RemoteStatus.WAITING), ("FAILED", RemoteStatus.FAILED), ("COMPLETED", RemoteStatus.SUCCEEDED),
        ("STATE_UNSPECIFIED", RemoteStatus.PENDING), ("SOMETHING_NEW", RemoteStatus.PENDING),
    ])
    async def test_states(self, state, status):
        server = FakeJules()
        c = connector(server)
        await c.launch(REQUEST)
        finish(server, "s1", state)
        assert (await c.get("s1")).status == status

    async def test_completed_session_exposes_its_pull_request(self):
        server = FakeJules()
        c = connector(server)
        await c.launch(REQUEST)
        finish(server, "s1", "COMPLETED", outputs=[{"pullRequest": {"url": "https://github.com/acme/demo/pull/9", "title": "Ajoute un README", "description": "d"}}])
        remote = await c.get("s1")
        assert remote.pr_url == "https://github.com/acme/demo/pull/9" and remote.summary == "Ajoute un README"

    async def test_failure_reason_comes_from_the_activities(self):
        server = FakeJules()
        c = connector(server)
        await c.launch(REQUEST)
        finish(server, "s1", "FAILED")
        server.activities["s1"] = [{"createTime": "2026-01-01T00:00:00Z", "sessionFailed": {"reason": "Les tests ne passent pas"}}]
        assert (await c.get("s1")).error_message == "Les tests ne passent pas"

    async def test_waiting_for_feedback_shows_the_agents_last_question(self):
        server = FakeJules()
        c = connector(server)
        await c.launch(REQUEST)
        finish(server, "s1", "AWAITING_USER_FEEDBACK")
        server.activities["s1"] = [
            {"createTime": "2026-01-01T00:00:01Z", "agentMessaged": {"agentMessage": "ancien"}},
            {"createTime": "2026-01-01T00:00:09Z", "agentMessaged": {"agentMessage": "Quelle version de Python ?"}},
        ]
        remote = await c.get("s1")
        assert remote.status == RemoteStatus.WAITING and "Quelle version de Python ?" in remote.error_message

    async def test_missing_activities_never_break_the_status(self):
        server = FakeJules()
        c = connector(server)
        await c.launch(REQUEST)
        finish(server, "s1", "FAILED")
        server.fail_activities = True
        remote = await c.get("s1")
        assert remote.status == RemoteStatus.FAILED and remote.error_message == "La session a échoué chez Jules."

    async def test_a_raw_script_log_is_reduced_to_its_cause(self):
        server = FakeJules()
        c = connector(server)
        await c.launch(REQUEST)
        finish(server, "s1", "FAILED")
        log = (
            "Jules encountered an error when cloning the repo.\n```+ sudo rm -rf /app\n+ sudo mkdir /app\n"
            + "+ git config --global core.hooksPath /dev/null\n" * 40
            + "+ git clone --depth 1 https://github.com/acme/demo -b main /app\n"
            + "Cloning into '/app'...\nfatal: Remote branch main not found in upstream origin\n```"
        )
        server.activities["s1"] = [{"createTime": "2026-01-01T00:00:00Z", "sessionFailed": {"reason": log}}]
        message = (await c.get("s1")).error_message
        assert message == "Jules encountered an error when cloning the repo. fatal: Remote branch main not found in upstream origin"

    @pytest.mark.parametrize("bad", ["../sessions", "a/b", "s1?x=1", "", "a b"])
    async def test_session_ids_cannot_change_the_request_path(self, bad):
        server = FakeJules()
        with pytest.raises(ConnectorError):
            await connector(server).get(bad)
        assert not server.requests

    async def test_cancel_is_explicitly_unsupported(self):
        with pytest.raises(ConnectorError) as exc:
            await connector(FakeJules()).cancel("s1")
        assert exc.value.category == ErrorCategory.UNSUPPORTED_CAPABILITY

    async def test_the_key_is_not_in_any_error_message(self):
        server = FakeJules()
        server.sources = []
        with pytest.raises(ConnectorError) as exc:
            await connector(server).launch(REQUEST)
        assert API_KEY not in exc.value.message


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()


@pytest.fixture
def server(monkeypatch, env):
    """Runner + registre branchés sur le faux serveur Jules."""
    fake = FakeJules()
    monkeypatch.setitem(
        registry._PROVIDERS, "jules",
        lambda secret: JulesConnector(secret, transport=httpx.MockTransport(fake), sleep=no_sleep),
    )
    return fake


async def jules_execution(prompt="Ajoute un README"):
    project = await service.create_project(ALICE, "demo", "https://github.com/acme/demo")
    integration = await runner.connect_integration(ALICE, "jules", API_KEY)
    task = await service.create_task(ALICE, str(project.id), str(integration.id), prompt)
    return integration, await service.create_execution(ALICE, str(task.id))


class TestThroughTheRunner:
    async def test_connecting_stores_capabilities_without_cancel(self, server):
        integration = await runner.connect_integration(ALICE, "jules", API_KEY)
        assert set(integration.capabilities) == {"launch", "status", "pull_request"}

    async def test_launch_follow_and_pull_request(self, server):
        _, execution = await jules_execution()
        launched = await runner.launch_execution(ALICE, str(execution.id))
        assert launched.status == S.RUNNING and launched.external_id == "s1"

        finish(server, "s1", "COMPLETED", outputs=[{"pullRequest": {"url": "https://github.com/acme/demo/pull/3", "title": "README"}}])
        done = await runner.refresh_execution(ALICE, str(execution.id))
        assert done.status == S.SUCCEEDED and done.pr_url == "https://github.com/acme/demo/pull/3"

    async def test_lost_launch_response_is_recovered_without_a_second_session(self, server):
        _, execution = await jules_execution()
        server.lose_next_create = True

        launched = await runner.launch_execution(ALICE, str(execution.id))

        assert launched.status == S.RUNNING and launched.external_id == "s1"
        assert len(server.sessions) == 1
        kinds = [e.kind for e in await service.list_events(ALICE, str(execution.id))]
        assert EventKind.RECONCILIATION in kinds

    async def test_unrecoverable_lost_launch_needs_attention_and_later_resolves(self, server):
        _, execution = await jules_execution()
        server.lose_next_create = True
        server.session_pages = [[]]  # la liste ne montre pas encore la session
        stuck = await runner.launch_execution(ALICE, str(execution.id))
        assert stuck.status == S.NEEDS_ATTENTION and len(server.sessions) == 1

        server.session_pages = None  # elle apparaît au passage suivant
        recovered = await runner.refresh_execution(ALICE, str(execution.id))
        assert recovered.status == S.RUNNING and recovered.external_id == "s1" and len(server.sessions) == 1

    async def test_waiting_for_the_user_is_surfaced_then_resumes(self, server):
        _, execution = await jules_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        finish(server, "s1", "AWAITING_USER_FEEDBACK")
        server.activities["s1"] = [{"createTime": "2026-01-01T00:00:09Z", "agentMessaged": {"agentMessage": "Quelle branche ?"}}]

        waiting = await runner.refresh_execution(ALICE, str(execution.id))
        assert waiting.status == S.NEEDS_ATTENTION and "Quelle branche ?" in waiting.error_message

        finish(server, "s1", "IN_PROGRESS")
        resumed = await runner.refresh_execution(ALICE, str(execution.id))
        assert resumed.status == S.RUNNING

    async def test_failure_carries_the_providers_reason(self, server):
        _, execution = await jules_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        finish(server, "s1", "FAILED")
        server.activities["s1"] = [{"createTime": "2026-01-01T00:00:00Z", "sessionFailed": {"reason": "Dépendances introuvables"}}]
        failed = await runner.refresh_execution(ALICE, str(execution.id))
        assert failed.status == S.FAILED and failed.error_message == "Dépendances introuvables"

    async def test_repository_not_installed_fails_with_a_helpful_message(self, server):
        server.sources = []
        _, execution = await jules_execution()
        failed = await runner.launch_execution(ALICE, str(execution.id))
        assert failed.status == S.FAILED and "application GitHub de Jules" in failed.error_message

    async def test_cancel_is_refused_explicitly(self, server):
        _, execution = await jules_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        with pytest.raises(ConnectorError) as exc:
            await runner.request_cancel(ALICE, str(execution.id))
        assert exc.value.category == ErrorCategory.UNSUPPORTED_CAPABILITY


class TestInterface:
    async def login(self):
        from src.models.user import User
        from src.web.auth import COOKIE_NAME, create_web_session

        admin = await User(telegram_id=ALICE, first_name="Ada", role="admin").insert()
        return {COOKIE_NAME: await create_web_session(admin)}

    async def test_cancel_button_is_hidden_when_the_provider_cannot_cancel(self, server, aclient):
        cookies = await self.login()
        _, execution = await jules_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        html = (await aclient.get(f"/dev/executions/{execution.id}", cookies=cookies)).text
        assert "Actualiser" in html and f"/dev/executions/{execution.id}/cancel" not in html

    async def test_cancel_button_is_shown_when_the_provider_can_cancel(self, env, aclient):
        cookies = await self.login()
        project = await service.create_project(ALICE, "demo", "https://github.com/acme/demo")
        integration = await runner.connect_integration(ALICE, "fake", "k")
        task = await service.create_task(ALICE, str(project.id), str(integration.id), "t [slow]")
        execution = await service.create_execution(ALICE, str(task.id))
        await runner.launch_execution(ALICE, str(execution.id))
        html = (await aclient.get(f"/dev/executions/{execution.id}", cookies=cookies)).text
        assert f"/dev/executions/{execution.id}/cancel" in html

    async def test_waiting_run_links_to_the_provider_session(self, server, aclient):
        cookies = await self.login()
        _, execution = await jules_execution()
        await runner.launch_execution(ALICE, str(execution.id))
        finish(server, "s1", "AWAITING_USER_FEEDBACK")
        server.activities["s1"] = [{"createTime": "2026-01-01T00:00:09Z", "agentMessaged": {"agentMessage": "Quelle branche ?"}}]
        await runner.refresh_execution(ALICE, str(execution.id))
        html = (await aclient.get(f"/dev/executions/{execution.id}", cookies=cookies)).text
        assert 'href="https://jules.google.com/session/s1"' in html and "Quelle branche ?" in html
        assert 'rel="noopener noreferrer"' in html

    async def test_connections_page_offers_jules_with_its_instructions(self, env, aclient):
        cookies = await self.login()
        html = (await aclient.get("/dev/integrations", cookies=cookies)).text
        assert '<option value="jules">Jules (Google)</option>' in html
        assert "application GitHub de Jules" in html


class TestNotificationForWaitingRuns:
    def test_the_notification_links_to_the_provider_for_a_waiting_run(self):
        from src.orbi_dev import notifier
        from src.orbi_dev.models import Execution

        ex = Execution(
            owner_id=1, task_id="t", integration_id="i", provider="jules", status=S.NEEDS_ATTENTION,
            idempotency_key="k", client_ref="r", external_url="https://jules.google.com/session/s1",
        )
        urls = [b.url for row in notifier.build_keyboard(ex).inline_keyboard for b in row if b.url]
        assert urls == ["https://jules.google.com/session/s1"]
        ex.external_url = "javascript:alert(1)"
        assert not [b for row in notifier.build_keyboard(ex).inline_keyboard for b in row if b.url]
