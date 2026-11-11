"""Tests du connecteur Devin (API v3) — réponses HTTP simulées d'après la spec OpenAPI officielle."""

import json

import httpx
import pytest

from src.orbi_dev.connectors.base import (
    Capability,
    ConnectorError,
    ErrorCategory,
    LaunchRequest,
    RemoteStatus,
)
from src.orbi_dev.connectors.devin import DevinConnector

API_KEY = "cog_super_secret_key_123456"
ORG = "org-abc123def456"
REF = "00000000-0000-0000-0000-000000000001"
SESSION = "devin-9f8e7d6c-1234-4abc-8def-000000000001"
REQUEST = LaunchRequest(REF, "Corrige le test en échec", "https://github.com/acme/demo", "main")

SELF_SERVICE = {"principal_type": "service_user", "service_user_id": "su-1", "service_user_name": "orbi", "org_id": ORG}
SELF_PAT = {
    "principal_type": "pat_user", "user_id": "u-1", "user_name": "dev",
    "api_key_id": "k-1", "api_key_name": "orbi", "devin_sessions_org_id": ORG, "org_id": None,
}


def session_body(status="running", **extra):
    return {"session_id": SESSION, "status": status, "status_detail": "working", "pull_requests": [], **extra}


class Recorder:
    """Transport simulé : répond dans l'ordre et mémorise les requêtes."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def connector(recorder, **kwargs):
    return DevinConnector(API_KEY, transport=httpx.MockTransport(recorder), **kwargs)


def json_response(status, body, headers=None):
    return httpx.Response(status, json=body, headers=headers)


def problem(status, detail="oops", title="Error", error_code=None):
    body = {"title": title, "status": status, "detail": detail}
    if error_code:
        body["error_code"] = error_code
    return json_response(status, body)


class TestVerifyAndOrg:
    async def test_verify_calls_self_and_declares_all_capabilities(self):
        rec = Recorder(json_response(200, SELF_SERVICE))
        result = await connector(rec).verify()
        req = rec.requests[0]
        assert (req.method, req.url.path) == ("GET", "/v3/self")
        assert req.headers["authorization"] == f"Bearer {API_KEY}"
        assert Capability.INTERACT in result.capabilities
        assert Capability.CANCEL in result.capabilities
        assert Capability.LAUNCH in result.capabilities
        assert Capability.PULL_REQUEST in result.capabilities

    async def test_launch_discovers_org_via_self_then_creates_session(self):
        rec = Recorder(
            json_response(200, SELF_PAT),  # GET /v3/self : org découverte (jeton personnel)
            json_response(200, session_body()),
        )
        remote = await connector(rec).launch(REQUEST)

        assert [r.url.path for r in rec.requests] == [
            "/v3/self", f"/v3/organizations/{ORG}/sessions",
        ]
        create = rec.requests[1]
        assert create.url.params["devin_id"] == f"devin-{REF}"
        assert json.loads(create.content) == {
            "prompt": "Corrige le test en échec",
            "repos": ["https://github.com/acme/demo"],
        }
        assert remote.external_id == SESSION
        assert remote.status == RemoteStatus.RUNNING
        assert remote.external_url == f"https://app.devin.ai/sessions/{SESSION}"

    async def test_org_is_cached_across_calls(self):
        rec = Recorder(json_response(200, SELF_SERVICE), json_response(200, session_body("exit")),
                       json_response(200, session_body("exit")))
        c = connector(rec)
        await c.get(SESSION)
        await c.get(SESSION)
        paths = [r.url.path for r in rec.requests]
        assert paths.count("/v3/self") == 1
        assert paths.count(f"/v3/organizations/{ORG}/sessions/{SESSION}") == 2

    async def test_key_without_usable_org_is_refused(self):
        rec = Recorder(json_response(200, {"principal_type": "pat_user", "org_id": None,
                                           "devin_sessions_org_id": None, "primary_billing_org_id": None}))
        with pytest.raises(ConnectorError) as exc:
            await connector(rec).launch(REQUEST)
        assert exc.value.category == ErrorCategory.PERMISSION_DENIED


class TestGet:
    @pytest.mark.parametrize(
        "body,expected",
        [
            (session_body("new"), RemoteStatus.PENDING),
            (session_body("claimed"), RemoteStatus.PENDING),
            (session_body("running"), RemoteStatus.RUNNING),
            (session_body("running", status_detail="waiting_for_user"), RemoteStatus.WAITING),
            (session_body("running", status_detail="waiting_for_approval"), RemoteStatus.WAITING),
            (session_body("resuming"), RemoteStatus.RUNNING),
            (session_body("exit"), RemoteStatus.SUCCEEDED),
            (session_body("error"), RemoteStatus.FAILED),
            (session_body("suspended"), RemoteStatus.WAITING),
            (session_body("unknown_future_state"), RemoteStatus.PENDING),
        ],
    )
    async def test_status_mapping(self, body, expected):
        rec = Recorder(json_response(200, SELF_SERVICE), json_response(200, body))
        assert (await connector(rec).get(SESSION)).status == expected

    async def test_pull_request_is_extracted(self):
        body = session_body("exit", pull_requests=[{"pr_url": "https://github.com/acme/demo/pull/42",
                                                  "pr_state": "open"}])
        rec = Recorder(json_response(200, SELF_SERVICE), json_response(200, body))
        remote = await connector(rec).get(SESSION)
        assert remote.pr_url == "https://github.com/acme/demo/pull/42"
        assert remote.status == RemoteStatus.SUCCEEDED

    async def test_waiting_and_failed_carry_a_reason(self):
        rec = Recorder(json_response(200, SELF_SERVICE),
                       json_response(200, session_body("running", status_detail="waiting_for_user")))
        assert (await connector(rec).get(SESSION)).error_message
        rec = Recorder(json_response(200, SELF_SERVICE), json_response(200, session_body("error")))
        assert (await connector(rec).get(SESSION)).error_message


class TestCancel:
    async def test_delete_terminates_and_reports_cancelled(self):
        rec = Recorder(json_response(200, SELF_SERVICE), httpx.Response(204))
        remote = await connector(rec).cancel(SESSION)
        assert rec.requests[1].method == "DELETE"
        assert rec.requests[1].url.path == f"/v3/organizations/{ORG}/sessions/{SESSION}"
        assert remote.status == RemoteStatus.CANCELLED

    async def test_invalid_session_id_cannot_escape_the_path(self):
        rec = Recorder()
        for bad in ("../self", "a/b", "", "x" * 200):
            with pytest.raises(ConnectorError) as exc:
                await connector(rec).get(bad)
            assert exc.value.category == ErrorCategory.INVALID_REQUEST
        assert not rec.requests


class TestSendInput:
    async def test_message_posts_to_the_session(self):
        rec = Recorder(json_response(200, SELF_SERVICE), json_response(200, session_body()))
        await connector(rec).send_input(SESSION, "Privilégie auth.py")
        req = rec.requests[1]
        assert (req.method, req.url.path) == ("POST", f"/v3/organizations/{ORG}/sessions/{SESSION}/messages")
        assert json.loads(req.content) == {"message": "Privilégie auth.py"}

    async def test_lost_response_is_not_retried(self):
        """Un message Devin n'est pas documenté idempotent : pas de second POST après un timeout."""
        rec = Recorder(json_response(200, SELF_SERVICE), *[httpx.ReadTimeout("slow")] * 3)
        with pytest.raises(ConnectorError) as exc:
            await connector(rec).send_input(SESSION, "salut")
        assert exc.value.outcome_unknown is True
        assert len(rec.requests) == 2  # self + un seul POST messages


class TestListMessages:
    async def test_messages_are_mapped_and_tail_limited(self):
        items = [
            {"event_id": f"e{i}", "source": "user" if i % 2 else "devin",
             "message": f"message {i}", "created_at": 1700000000 + i}
            for i in range(5)
        ]
        rec = Recorder(json_response(200, SELF_SERVICE),
                       json_response(200, {"items": items, "has_next_page": False, "end_cursor": None}))
        messages = await connector(rec).list_messages(SESSION, limit=3)

        assert [m.role for m in messages] == ["agent", "user", "agent"]
        assert [m.text for m in messages] == ["message 2", "message 3", "message 4"]
        assert messages[0].at is not None
        assert rec.requests[1].url.params["first"] == "200"

    async def test_empty_thread_is_an_empty_list(self):
        rec = Recorder(json_response(200, SELF_SERVICE), json_response(200, {"items": []}))
        assert await connector(rec).list_messages(SESSION) == []

    async def test_history_is_declared(self):
        rec = Recorder(json_response(200, SELF_SERVICE), json_response(200, {"items": []}))
        result = await connector(rec).verify()
        assert Capability.HISTORY in result.capabilities


class TestErrors:
    @pytest.mark.parametrize(
        "status,body,category",
        [
            (401, {"title": "Unauthorized", "status": 401, "detail": "bad key"}, ErrorCategory.AUTH_INVALID),
            (403, {"title": "Forbidden", "status": 403, "detail": "no perm"}, ErrorCategory.PERMISSION_DENIED),
            (403, {"title": "Forbidden", "status": 403, "detail": "x", "error_code": "user_frozen"},
             ErrorCategory.PERMISSION_DENIED),
            (404, {"title": "Not Found", "status": 404, "detail": "no session"}, ErrorCategory.NOT_FOUND),
            (409, {"title": "Conflict", "status": 409, "detail": "busy"}, ErrorCategory.CONFLICT),
            (410, {"title": "Gone", "status": 410, "detail": "terminated"}, ErrorCategory.NOT_FOUND),
            (422, {"title": "Unprocessable", "status": 422, "detail": "bad prompt"}, ErrorCategory.INVALID_REQUEST),
            (429, {"title": "Too Many", "status": 429, "detail": "slow"}, ErrorCategory.RATE_LIMITED),
            (500, {"title": "Err", "status": 500, "detail": "oops"}, ErrorCategory.UNAVAILABLE),
        ],
    )
    async def test_problem_detail_mapping(self, status, body, category):
        rec = Recorder(problem(status, body.get("detail"), body["title"], body.get("error_code")))
        with pytest.raises(ConnectorError) as exc:
            await connector(rec, max_retries=0).verify()
        assert exc.value.category == category

    async def test_provider_detail_is_sanitized_and_key_never_leaks(self):
        rec = Recorder(problem(400, f"bad header Bearer {API_KEY} and <script>"))
        with pytest.raises(ConnectorError) as exc:
            await connector(rec, max_retries=0).verify()
        assert API_KEY not in exc.value.message
