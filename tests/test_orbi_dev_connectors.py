"""Tests du contrat de connecteur et de l'adaptateur Cursor (réponses HTTP simulées)."""

import json

import httpx
import pytest

from src.core.config import get_settings
from src.orbi_dev.connectors.base import (
    BaseConnector,
    Capability,
    ConnectorError,
    ErrorCategory,
    LaunchRequest,
    RemoteStatus,
)
from src.orbi_dev.connectors.cursor import CursorCloudAgentsConnector
from src.orbi_dev.connectors.registry import available_providers, build_connector

API_KEY = "crsr_super_secret_key_123456"
REF = "00000000-0000-0000-0000-000000000001"
AGENT_ID = f"bc-{REF}"
REQUEST = LaunchRequest(REF, "Ajoute un README", "https://github.com/acme/demo", "main")

AGENT = {"id": AGENT_ID, "status": "ACTIVE", "url": f"https://cursor.com/agents/{AGENT_ID}", "latestRunId": "run-1"}


def run_body(status="RUNNING", **extra):
    return {"id": "run-1", "agentId": AGENT_ID, "status": status, **extra}


class Recorder:
    """Transport simulé : renvoie les réponses dans l'ordre et mémorise les requêtes."""

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
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    c = CursorCloudAgentsConnector(
        API_KEY, transport=httpx.MockTransport(recorder), sleep=fake_sleep, **kwargs
    )
    c.slept = slept  # type: ignore[attr-defined]
    return c


def json_response(status, body, headers=None):
    return httpx.Response(status, json=body, headers=headers)


class TestStartingRef:
    async def test_cursor_omits_startingref_when_no_branch_is_chosen(self):
        rec = Recorder(json_response(201, {"agent": AGENT, "run": run_body("CREATING")}))
        await connector(rec).launch(LaunchRequest(REF, "p", "https://github.com/acme/demo", ""))
        assert "startingRef" not in json.loads(rec.requests[0].content)["repos"][0]

    async def test_cursor_sends_the_chosen_branch(self):
        rec = Recorder(json_response(201, {"agent": AGENT, "run": run_body("CREATING")}))
        await connector(rec).launch(LaunchRequest(REF, "p", "https://github.com/acme/demo", "develop"))
        assert json.loads(rec.requests[0].content)["repos"][0]["startingRef"] == "develop"


class TestLaunch:
    async def test_request_shape_and_result(self):
        rec = Recorder(json_response(201, {"agent": AGENT, "run": run_body("CREATING")}))

        remote = await connector(rec).launch(REQUEST)

        req = rec.requests[0]
        assert (req.method, req.url.path) == ("POST", "/v1/agents")
        assert req.headers["authorization"] == f"Bearer {API_KEY}"
        body = json.loads(req.content)
        assert body["agentId"] == AGENT_ID
        assert body["prompt"] == {"text": "Ajoute un README"}
        assert body["repos"] == [{"url": "https://github.com/acme/demo", "startingRef": "main"}]
        assert body["autoCreatePR"] is True
        assert remote.status == RemoteStatus.PENDING
        assert remote.external_id == AGENT_ID

    async def test_duplicate_agent_id_is_adopted_not_failed(self):
        rec = Recorder(
            json_response(409, {"error": {"code": "agent_id_conflict", "message": "exists"}}),
            json_response(200, AGENT),
            json_response(200, run_body("RUNNING")),
        )

        remote = await connector(rec).launch(REQUEST)

        assert remote.status == RemoteStatus.RUNNING
        assert [r.method for r in rec.requests] == ["POST", "GET", "GET"]

    async def test_lost_response_is_retried_safely_thanks_to_agent_id(self):
        rec = Recorder(httpx.ReadTimeout("slow"), json_response(201, {"agent": AGENT, "run": run_body("CREATING")}))
        c = connector(rec)

        remote = await c.launch(REQUEST)

        assert remote.external_id == AGENT_ID
        assert len(rec.requests) == 2
        assert json.loads(rec.requests[0].content)["agentId"] == json.loads(rec.requests[1].content)["agentId"]
        assert len(c.slept) == 1

    async def test_persistent_read_timeout_reports_unknown_outcome(self):
        rec = Recorder(*[httpx.ReadTimeout("slow")] * 3)

        with pytest.raises(ConnectorError) as exc:
            await connector(rec).launch(REQUEST)

        assert exc.value.category == ErrorCategory.TIMEOUT
        assert exc.value.outcome_unknown is True
        assert len(rec.requests) == 3  # 1 essai + 2 retries bornés

    async def test_connect_error_is_known_not_sent(self):
        rec = Recorder(*[httpx.ConnectError("refused")] * 3)

        with pytest.raises(ConnectorError) as exc:
            await connector(rec).launch(REQUEST)

        assert exc.value.category == ErrorCategory.UNAVAILABLE
        assert exc.value.outcome_unknown is False

    async def test_rate_limit_honours_retry_after(self):
        rec = Recorder(
            json_response(429, {"error": {"code": "rate_limit_exceeded", "message": "slow down"}}, {"Retry-After": "7"}),
            json_response(201, {"agent": AGENT, "run": run_body("CREATING")}),
        )
        c = connector(rec)

        await c.launch(REQUEST)

        assert c.slept == [7.0]

    async def test_non_retryable_error_is_not_retried(self):
        rec = Recorder(json_response(403, {"error": {"code": "plan_required", "message": "Upgrade"}}))

        with pytest.raises(ConnectorError) as exc:
            await connector(rec).launch(REQUEST)

        assert exc.value.category == ErrorCategory.PLAN_OR_QUOTA
        assert len(rec.requests) == 1


class TestGet:
    async def test_finished_run_exposes_pr_branch_and_summary(self):
        git = {"branches": [{"repoUrl": "github.com/acme/demo", "branch": "cursor/readme", "prUrl": "https://github.com/acme/demo/pull/9"}]}
        rec = Recorder(json_response(200, AGENT), json_response(200, run_body("FINISHED", result="Fait.", git=git)))

        remote = await connector(rec).get(AGENT_ID)

        assert remote.status == RemoteStatus.SUCCEEDED
        assert remote.pr_url == "https://github.com/acme/demo/pull/9"
        assert remote.branch == "cursor/readme"
        assert remote.summary == "Fait."
        assert remote.external_url == AGENT["url"]

    @pytest.mark.parametrize(
        "provider_status,expected",
        [("CREATING", RemoteStatus.PENDING), ("RUNNING", RemoteStatus.RUNNING), ("ERROR", RemoteStatus.FAILED),
         ("CANCELLED", RemoteStatus.CANCELLED), ("EXPIRED", RemoteStatus.EXPIRED)],
    )
    async def test_status_mapping(self, provider_status, expected):
        rec = Recorder(json_response(200, AGENT), json_response(200, run_body(provider_status)))
        assert (await connector(rec).get(AGENT_ID)).status == expected

    async def test_failed_run_carries_error_message(self):
        rec = Recorder(json_response(200, AGENT), json_response(200, run_body("ERROR", result="Tests en échec")))
        remote = await connector(rec).get(AGENT_ID)
        assert remote.error_message == "Tests en échec"

    async def test_archived_agent_with_unfinished_run_is_expired(self):
        rec = Recorder(json_response(200, {**AGENT, "status": "ARCHIVED"}), json_response(200, run_body("RUNNING")))
        assert (await connector(rec).get(AGENT_ID)).status == RemoteStatus.EXPIRED

    async def test_agent_without_run_is_pending(self):
        rec = Recorder(json_response(200, {**AGENT, "latestRunId": None}))
        assert (await connector(rec).get(AGENT_ID)).status == RemoteStatus.PENDING

    async def test_get_retries_transient_unavailability(self):
        rec = Recorder(json_response(503, {"error": {"code": "upstream_error", "message": "x"}}),
                       json_response(200, AGENT), json_response(200, run_body("RUNNING")))
        assert (await connector(rec).get(AGENT_ID)).status == RemoteStatus.RUNNING


class TestCancel:
    async def test_cancel_posts_to_the_active_run_then_rereads(self):
        rec = Recorder(json_response(200, AGENT), json_response(200, {}), json_response(200, AGENT),
                       json_response(200, run_body("CANCELLED")))

        remote = await connector(rec).cancel(AGENT_ID)

        assert [(r.method, r.url.path) for r in rec.requests][:2] == [
            ("GET", f"/v1/agents/{AGENT_ID}"), ("POST", f"/v1/agents/{AGENT_ID}/runs/run-1/cancel")]
        assert remote.status == RemoteStatus.CANCELLED

    async def test_not_cancellable_is_a_conflict_and_not_retried(self):
        rec = Recorder(json_response(200, AGENT),
                       json_response(409, {"error": {"code": "run_not_cancellable", "message": "done"}}))

        with pytest.raises(ConnectorError) as exc:
            await connector(rec).cancel(AGENT_ID)

        assert exc.value.category == ErrorCategory.CONFLICT
        assert exc.value.code == "run_not_cancellable"
        assert len(rec.requests) == 2


class TestVerify:
    async def test_read_only_probe(self):
        rec = Recorder(json_response(200, {"items": []}))

        result = await connector(rec).verify()

        assert (rec.requests[0].method, rec.requests[0].url.path, rec.requests[0].url.params["limit"]) == ("GET", "/v1/agents", "1")
        assert Capability.LAUNCH in result.capabilities

    async def test_invalid_key(self):
        rec = Recorder(json_response(401, {"code": "error", "message": "Invalid User API Key"}))
        with pytest.raises(ConnectorError) as exc:
            await connector(rec).verify()
        assert exc.value.category == ErrorCategory.AUTH_INVALID


class TestErrorMapping:
    @pytest.mark.parametrize(
        "status,body,category",
        [
            (401, {"code": "error", "message": "Invalid User API Key"}, ErrorCategory.AUTH_INVALID),
            (401, {"error": {"code": "unauthorized", "message": "no"}}, ErrorCategory.AUTH_INVALID),
            (403, {"error": {"code": "repository_access", "message": "no access"}}, ErrorCategory.PERMISSION_DENIED),
            (403, {"error": {"code": "plan_required", "message": "plan"}}, ErrorCategory.PLAN_OR_QUOTA),
            (429, {"error": {"code": "usage_limit_exceeded", "message": "quota"}}, ErrorCategory.PLAN_OR_QUOTA),
            (404, {"error": {"code": "agent_not_found", "message": "gone"}}, ErrorCategory.NOT_FOUND),
            (409, {"error": {"code": "agent_busy", "message": "busy"}}, ErrorCategory.CONFLICT),
            (400, {"error": {"code": "validation_error", "message": "bad"}}, ErrorCategory.INVALID_REQUEST),
            (500, {"error": {"code": "internal_error", "message": "oops"}}, ErrorCategory.UNAVAILABLE),
            (418, {"weird": True}, ErrorCategory.UNKNOWN),
        ],
    )
    async def test_categories(self, status, body, category):
        rec = Recorder(*[json_response(status, body)] * 5)
        with pytest.raises(ConnectorError) as exc:
            await connector(rec, max_retries=0).get(AGENT_ID)
        assert exc.value.category == category

    async def test_non_json_error_body_is_handled(self):
        rec = Recorder(httpx.Response(502, text="<html>Bad gateway</html>"))
        with pytest.raises(ConnectorError) as exc:
            await connector(rec, max_retries=0).get(AGENT_ID)
        assert exc.value.category == ErrorCategory.UNAVAILABLE
        assert "<html>" not in exc.value.message

    async def test_provider_message_echoing_the_key_is_redacted(self):
        body = {"error": {"code": "validation_error", "message": f"bad header Authorization: Bearer {API_KEY}"}}
        rec = Recorder(json_response(400, body))
        with pytest.raises(ConnectorError) as exc:
            await connector(rec, max_retries=0).get(AGENT_ID)
        assert API_KEY not in exc.value.message
        assert API_KEY not in repr(exc.value)

    async def test_key_is_never_logged(self, caplog):
        import logging

        rec = Recorder(json_response(503, {"error": {"code": "upstream_error", "message": "x"}}),
                       json_response(200, AGENT), json_response(200, run_body("RUNNING")))
        with caplog.at_level(logging.DEBUG):
            await connector(rec).get(AGENT_ID)
        assert API_KEY not in caplog.text


class TestContractAndRegistry:
    async def test_unsupported_operations_fail_explicitly(self):
        base = BaseConnector()
        base.provider = "x"
        for call in (base.launch(REQUEST), base.get("id"), base.cancel("id")):
            with pytest.raises(ConnectorError) as exc:
                await call
            assert exc.value.category == ErrorCategory.UNSUPPORTED_CAPABILITY

    def test_fake_is_never_available_in_production(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("JWT_SECRET", "x" * 40)
        get_settings.cache_clear()
        assert "fake" not in available_providers()
        with pytest.raises(ConnectorError):
            build_connector("fake", "k")

    def test_providers_in_development(self):
        assert set(available_providers()) == {"cursor", "jules", "fake"}

    def test_unknown_provider(self):
        with pytest.raises(ConnectorError):
            build_connector("nope", "k")
