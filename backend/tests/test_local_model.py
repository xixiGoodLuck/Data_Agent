from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.llm import (
    LOCAL_MODEL_MAX_TOKENS,
    LOCAL_NON_THINKING_EXTRA_BODY,
    MockLLMClient,
    OpenAICompatibleLLMClient,
    get_local_model_client,
)
from app.core.errors import AppError
from app.models import ApprovalRequest, QueryLog
from app.schemas.query import normalize_local_base_url


class LocalModelStub(MockLLMClient):
    provider_name = "local"


def install_local_stub(monkeypatch, captured: list[tuple[str, str]]) -> None:
    def factory(_settings, base_url: str, model: str):
        captured.append((base_url, model))
        return LocalModelStub()

    monkeypatch.setattr("app.agent.service.get_local_model_client", factory)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://127.0.0.1:1234", "http://127.0.0.1:1234/v1"),
        ("http://127.0.0.1:1234/", "http://127.0.0.1:1234/v1"),
        ("http://127.0.0.1:1234/v1", "http://127.0.0.1:1234/v1"),
        ("http://127.0.0.1:1234/v1/", "http://127.0.0.1:1234/v1"),
        ("http://host.docker.internal:1234", "http://host.docker.internal:1234/v1"),
    ],
)
def test_local_base_url_is_normalized_once(value: str, expected: str) -> None:
    assert normalize_local_base_url(value) == expected


def test_local_model_request_overrides_mock_provider(
    client: TestClient, metadata, monkeypatch
) -> None:
    captured: list[tuple[str, str]] = []
    install_local_stub(monkeypatch, captured)

    response = client.post(
        "/api/query/stream",
        json={
            "dataset_id": "commerce",
            "question": "Which city has the highest order revenue?",
            "request_id": "local-model-overrides-mock",
            "local_model": {
                "enabled": True,
                "base_url": "http://127.0.0.1:1234",
                "model": "qwen3.5-0.8b",
            },
        },
    )

    assert response.status_code == 200
    assert "event: result" in response.text
    assert captured == [("http://127.0.0.1:1234/v1", "qwen3.5-0.8b")]
    assert client.app.state.llm_resolver.temporary_count == 0
    with metadata.session() as session:
        query_log = session.scalar(
            select(QueryLog).where(QueryLog.request_id == "local-model-overrides-mock")
        )
        assert query_log is not None
        assert query_log.llm_provider == "local"
        assert query_log.used_fallback is False


def test_disabled_local_model_preserves_mock_provider(
    client: TestClient, metadata, monkeypatch
) -> None:
    def unexpected_factory(*_args, **_kwargs):
        raise AssertionError("disabled local model must not create a local client")

    monkeypatch.setattr("app.agent.service.get_local_model_client", unexpected_factory)
    response = client.post(
        "/api/query",
        json={
            "dataset_id": "sales",
            "question": "Which region generated the most revenue?",
            "request_id": "disabled-local-model-uses-mock",
            "local_model": {"enabled": False, "base_url": "", "model": ""},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    with metadata.session() as session:
        query_log = session.scalar(
            select(QueryLog).where(QueryLog.request_id == "disabled-local-model-uses-mock")
        )
        assert query_log is not None
        assert query_log.llm_provider == "mock"


@pytest.mark.parametrize(
    ("configured_key", "expected_key"), [("", "local"), ("sk-existing", "sk-existing")]
)
def test_local_client_uses_existing_key_or_placeholder(
    test_settings, monkeypatch, configured_key: str, expected_key: str
) -> None:
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("app.agent.llm.ChatOpenAI", FakeChatOpenAI)
    settings = test_settings.model_copy(update={"openai_api_key": configured_key})

    client = get_local_model_client(settings, "http://127.0.0.1:1234/v1", "qwen3.5-0.8b")

    assert captured["api_key"] == expected_key
    assert captured["base_url"] == "http://127.0.0.1:1234/v1"
    assert captured["model"] == "qwen3.5-0.8b"
    assert captured["max_tokens"] == LOCAL_MODEL_MAX_TOKENS
    assert captured["extra_body"] == LOCAL_NON_THINKING_EXTRA_BODY
    assert captured["reasoning_effort"] == "none"
    assert isinstance(client, OpenAICompatibleLLMClient)
    assert client.structured_output_method == "json_schema"


def test_all_local_model_calls_inherit_non_thinking_client_options(
    test_settings, monkeypatch
) -> None:
    calls: list[tuple[str, dict[str, object], dict[str, object]]] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.request_options = kwargs

        def with_structured_output(self, schema, **kwargs):
            calls.append((schema.__name__, self.request_options, kwargs))
            return lambda _inputs: schema.model_construct()

    monkeypatch.setattr("app.agent.llm.ChatOpenAI", FakeChatOpenAI)
    client = get_local_model_client(test_settings, "http://127.0.0.1:1234/v1", "qwen3.5-0.8b")
    intent = client.fallback.understand_analysis_intent("Compare revenue", "en")
    plan = client.fallback.create_analysis_plan("Compare revenue", intent, "en")

    client.rewrite_question("Compare revenue", [], "en")
    client.understand_analysis_intent("Compare revenue", "en")
    client.create_analysis_plan("Compare revenue", intent, "en")
    client.select_tables("sales", "Compare revenue", {}, "en")
    client.generate_sql("sales", "Compare revenue", [], {}, "schema")
    client.repair_sql("sales", "Compare revenue", "SELECT 1", "syntax", "schema")
    client.evaluate_analysis(intent, plan, [], "en")
    client.synthesize_analysis("Compare revenue", intent, plan, [], None, False, "en")
    client.write_insight("Compare revenue", "SELECT 1", [], [], "en")

    assert [name for name, _options, _kwargs in calls] == [
        "QuestionRewrite",
        "AnalysisIntent",
        "AnalysisPlan",
        "TableSelection",
        "SqlGeneration",
        "SqlRepair",
        "AnalysisEvaluation",
        "FinalAnalysis",
        "InsightOutput",
    ]
    for _name, request_options, call_kwargs in calls:
        assert request_options["extra_body"] == LOCAL_NON_THINKING_EXTRA_BODY
        assert request_options["reasoning_effort"] == "none"
        assert call_kwargs == {"method": "json_schema"}


def test_local_model_invalid_structured_output_never_uses_mock_fallback() -> None:
    fallback_called = False

    class FakeChain:
        def invoke(self, _inputs):
            raise ValueError("tool calling unavailable")

    class FakePrompt:
        def __or__(self, _other):
            return FakeChain()

    class FakeModel:
        def with_structured_output(self, _schema, **_kwargs):
            return object()

    def fallback():
        nonlocal fallback_called
        fallback_called = True
        return object()

    llm = object.__new__(OpenAICompatibleLLMClient)
    llm.model = FakeModel()
    llm.last_used_fallback = False
    llm.allow_mock_fallback = False
    llm.provider_name = "local"
    llm.structured_output_method = "json_schema"

    with pytest.raises(AppError) as caught:
        llm._invoke_structured(FakePrompt(), object, {}, fallback)

    assert caught.value.error_type == "local_model_error"
    assert "tool-calling" in caught.value.message
    assert fallback_called is False
    assert llm.last_used_fallback is False


def test_local_model_failure_is_streamed_and_records_elapsed_time(
    client: TestClient, metadata, monkeypatch
) -> None:
    class FailingLocalModel(LocalModelStub):
        def rewrite_question(self, question, history, response_language="en"):
            del response_language
            time.sleep(0.01)
            raise AppError("local_model_error", "Local model capability error.", status_code=502)

    monkeypatch.setattr(
        "app.agent.service.get_local_model_client",
        lambda _settings, _base_url, _model: FailingLocalModel(),
    )
    response = client.post(
        "/api/query/stream",
        json={
            "dataset_id": "commerce",
            "question": "Which city has the highest order revenue?",
            "request_id": "local-model-explicit-failure",
            "local_model": {
                "enabled": True,
                "base_url": "http://127.0.0.1:1234",
                "model": "qwen3.5-0.8b",
            },
        },
    )

    assert "event: error" in response.text
    assert "local_model_error" in response.text
    assert "Local model capability error." in response.text
    with metadata.session() as session:
        query_log = session.scalar(
            select(QueryLog).where(QueryLog.request_id == "local-model-explicit-failure")
        )
        assert query_log is not None
        assert query_log.status == "failed"
        assert query_log.execution_time_ms > 0
        assert query_log.error_type == "local_model_error"


def test_local_model_approval_requires_same_request_override(
    client: TestClient, metadata, monkeypatch
) -> None:
    captured: list[tuple[str, str]] = []
    install_local_stub(monkeypatch, captured)
    local_model = {
        "enabled": True,
        "base_url": "http://127.0.0.1:1234",
        "model": "qwen3.5-0.8b",
    }
    pending = client.post(
        "/api/query",
        json={
            "dataset_id": "employees",
            "question": "List employee names and individual salary values.",
            "request_id": "local-model-approval",
            "local_model": local_model,
        },
    ).json()
    approval_id = pending["approval"]["id"]

    missing_override = client.post(f"/api/approvals/{approval_id}/approve", json={})
    assert missing_override.status_code == 400
    assert missing_override.json()["error"]["type"] == "local_model_error"
    with metadata.session() as session:
        approval = session.get(ApprovalRequest, approval_id)
        assert approval is not None
        assert approval.status == "pending"

    resumed = client.post(
        f"/api/approvals/{approval_id}/approve",
        json={"local_model": local_model},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "success"
    assert captured == [
        ("http://127.0.0.1:1234/v1", "qwen3.5-0.8b"),
        ("http://127.0.0.1:1234/v1", "qwen3.5-0.8b"),
    ]
