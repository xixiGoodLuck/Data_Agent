from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.llm import DEEPSEEK_MAX_TOKENS, MockLLMClient, OpenAICompatibleLLMClient
from app.core.errors import AppError
from app.evals.runner import EvalRunner, load_eval_cases
from app.models import ApprovalRequest, EvalRun, QueryLog


class DeepSeekStub(MockLLMClient):
    provider_name = "deepseek"


def install_deepseek_stub(monkeypatch, captured_keys: list[str]) -> None:
    def factory(_settings, api_key: str):
        captured_keys.append(api_key)
        return DeepSeekStub()

    monkeypatch.setattr("app.agent.service.get_deepseek_client", factory)


def test_temporary_key_selects_deepseek_and_is_not_persisted(
    client: TestClient, metadata, test_settings, monkeypatch
) -> None:
    secret = "sk-temporary-deepseek-test"
    request_id = "temporary-deepseek-request"
    captured_keys: list[str] = []
    install_deepseek_stub(monkeypatch, captured_keys)

    response = client.post(
        "/api/query/stream",
        headers={"X-DeepSeek-API-Key": secret},
        json={
            "dataset_id": "sales",
            "question": "Which region generated the most revenue?",
            "request_id": request_id,
        },
    )

    assert response.status_code == 200
    assert "event: result" in response.text
    assert secret not in response.text
    assert captured_keys == [secret]
    assert client.app.state.llm_resolver.temporary_count == 0

    with metadata.session() as session:
        query_log = session.scalar(select(QueryLog).where(QueryLog.request_id == request_id))
        assert query_log is not None
        assert query_log.llm_provider == "deepseek"
        assert secret not in json.dumps(
            {column.name: getattr(query_log, column.name) for column in QueryLog.__table__.columns},
            default=str,
        )

    for path in test_settings.runtime_dir.rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes()


def test_deepseek_approval_requires_key_again_and_can_resume(
    client: TestClient, metadata, monkeypatch
) -> None:
    secret = "sk-temporary-approval-test"
    captured_keys: list[str] = []
    install_deepseek_stub(monkeypatch, captured_keys)

    pending = client.post(
        "/api/query",
        headers={"X-DeepSeek-API-Key": secret},
        json={
            "dataset_id": "employees",
            "question": "List employee names and individual salary values.",
            "request_id": "temporary-deepseek-approval",
        },
    )

    assert pending.status_code == 200
    assert pending.json()["status"] == "pending_approval"
    approval_id = pending.json()["approval"]["id"]
    assert client.app.state.llm_resolver.temporary_count == 0

    missing_key = client.post(
        f"/api/approvals/{approval_id}/approve",
        json={"note": "reviewed"},
    )
    assert missing_key.status_code == 401
    assert missing_key.json()["error"]["type"] == "llm_auth_error"

    with metadata.session() as session:
        approval = session.get(ApprovalRequest, approval_id)
        assert approval is not None
        assert approval.status == "pending"

    approved = client.post(
        f"/api/approvals/{approval_id}/approve",
        headers={"X-DeepSeek-API-Key": secret},
        json={"note": "reviewed"},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "success"
    assert captured_keys == [secret, secret]
    assert client.app.state.llm_resolver.temporary_count == 0


def test_malformed_temporary_key_is_rejected_before_query(client: TestClient) -> None:
    response = client.post(
        "/api/query",
        headers={"X-DeepSeek-API-Key": "sk-invalid key"},
        json={
            "dataset_id": "sales",
            "question": "Show total revenue.",
            "request_id": "malformed-temporary-key",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "llm_auth_error"
    assert client.app.state.llm_resolver.temporary_count == 0


def test_eval_stream_uses_temporary_key_for_every_case_and_never_persists_it(
    client: TestClient, test_settings, monkeypatch
) -> None:
    secret = "sk-temporary-eval-test"
    captured_keys: list[str] = []
    install_deepseek_stub(monkeypatch, captured_keys)
    cases = load_eval_cases()[:2]
    monkeypatch.setattr("app.evals.runner.load_eval_cases", lambda: cases)

    response = client.post(
        "/api/evals/run/stream",
        headers={"X-DeepSeek-API-Key": secret},
    )

    assert response.status_code == 200
    assert "event: result" in response.text
    assert secret not in response.text
    assert captured_keys == [secret, secret]
    assert client.app.state.llm_resolver.temporary_count == 0
    for path in test_settings.runtime_dir.rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes()


def test_closing_eval_stream_releases_temporary_client(
    client: TestClient, metadata, monkeypatch
) -> None:
    secret = "sk-temporary-cancel-test"
    captured_keys: list[str] = []
    install_deepseek_stub(monkeypatch, captured_keys)
    cases = load_eval_cases()[:1]
    monkeypatch.setattr("app.evals.runner.load_eval_cases", lambda: cases)
    events = EvalRunner(metadata, client.app.state.query_service).stream(deepseek_api_key=secret)

    assert next(events)["event"] == "progress"
    assert next(events)["event"] == "progress"
    assert client.app.state.llm_resolver.temporary_count == 1

    events.close()

    assert client.app.state.llm_resolver.temporary_count == 0
    with metadata.session() as session:
        assert session.query(EvalRun).count() == 0


def test_deepseek_client_disables_thinking_and_caps_output(test_settings, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("app.agent.llm.ChatOpenAI", FakeChatOpenAI)

    from app.agent.llm import get_deepseek_client

    client = get_deepseek_client(test_settings, "sk-settings-test")

    assert captured["model"] == "deepseek-v4-flash"
    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["extra_body"] == {
        "thinking": {"type": "disabled"},
        "max_tokens": DEEPSEEK_MAX_TOKENS,
    }
    assert client.allow_mock_fallback is False


def test_structured_output_uses_provider_compatible_function_calling() -> None:
    captured: dict[str, object] = {}

    class DummyOutput:
        @classmethod
        def model_validate(cls, _value):
            return cls()

    class FakeChain:
        def invoke(self, _inputs):
            return DummyOutput()

    class FakePrompt:
        def __or__(self, _other):
            return FakeChain()

    class FakeModel:
        def with_structured_output(self, schema, **kwargs):
            captured["schema"] = schema
            captured.update(kwargs)
            return object()

    llm = object.__new__(OpenAICompatibleLLMClient)
    llm.model = FakeModel()
    llm.last_used_fallback = False
    llm.structured_output_method = "function_calling"

    result = llm._invoke_structured(FakePrompt(), DummyOutput, {}, DummyOutput)

    assert isinstance(result, DummyOutput)
    assert captured == {"schema": DummyOutput, "method": "function_calling"}


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, "llm_auth_error"),
        (403, "llm_auth_error"),
        (402, "llm_balance_error"),
        (429, "llm_rate_limit"),
        (400, "llm_request_error"),
        (422, "llm_request_error"),
        (500, "llm_provider_error"),
        (503, "llm_provider_error"),
    ],
)
def test_provider_http_errors_never_fall_back(status_code: int, error_type: str) -> None:
    class ProviderError(Exception):
        def __init__(self) -> None:
            self.status_code = status_code

    with pytest.raises(AppError) as caught:
        OpenAICompatibleLLMClient._raise_provider_error(ProviderError())

    assert caught.value.error_type == error_type
