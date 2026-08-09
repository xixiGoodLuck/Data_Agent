from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.llm import MockLLMClient
from app.agent.prompts import ANALYSIS_PLAN_PROMPT
from app.schemas.query import (
    MAX_ANALYSIS_STEPS,
    AnalysisPlan,
    AnalysisStep,
)


def ask(client: TestClient, dataset_id: str, question: str) -> dict:
    response = client.post(
        "/api/query",
        json={"dataset_id": dataset_id, "question": question},
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    ("dataset_id", "question", "analysis_type"),
    [
        ("sales", "总收入是多少?", "lookup"),
        ("commerce", "哪个城市收入最高?", "ranking"),
        ("sales", "显示月度收入趋势。", "trend"),
    ],
)
def test_direct_questions_use_simple_query_path(
    client: TestClient,
    dataset_id: str,
    question: str,
    analysis_type: str,
) -> None:
    body = ask(client, dataset_id, question)

    assert body["status"] == "success"
    assert body["analysis_mode"] == "simple_query"
    assert body["analysis_intent"]["analysis_type"] == analysis_type
    assert body["analysis_intent"]["needs_multi_step"] is False
    assert body["analysis_plan"] is None
    assert not any(event["node_name"] == "create_analysis_plan_node" for event in body["trace"])


@pytest.mark.parametrize(
    ("question", "analysis_type"),
    [
        ("为什么收入下降?", "diagnostic"),
        ("Why did revenue decline?", "diagnostic"),
        ("帮我分析这个数据有什么值得关注的问题。", "exploratory"),
    ],
)
def test_complex_questions_create_a_bounded_analysis_plan(
    client: TestClient,
    question: str,
    analysis_type: str,
) -> None:
    body = ask(client, "sales", question)

    assert body["status"] == "success"
    assert body["analysis_mode"] == "investigative_analysis"
    assert body["analysis_intent"]["analysis_type"] == analysis_type
    assert body["analysis_intent"]["needs_multi_step"] is True
    assert body["analysis_plan"]["max_steps"] == MAX_ANALYSIS_STEPS
    assert 1 <= len(body["analysis_plan"]["steps"]) <= MAX_ANALYSIS_STEPS
    assert body["analysis_plan"]["steps"][0]["status"] == "completed"
    assert body["analysis_step_count"] >= 2
    assert len(body["evidence"]) == body["analysis_step_count"]


def test_investigative_phase_executes_the_bounded_agent_loop(client: TestClient) -> None:
    body = ask(client, "sales", "Why did revenue decline?")

    executed = [event for event in body["trace"] if event["event_type"] == "query_executed"]
    assert len(executed) >= 2
    assert sum(
        event["node_name"] == "generate_sql_node" and event["event_type"] == "sql_generated"
        for event in body["trace"]
    ) == len(executed)
    assert any(event["event_type"] == "analysis_intent_created" for event in body["trace"])
    assert any(event["event_type"] == "analysis_plan_created" for event in body["trace"])


def test_simple_question_does_not_call_planner(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = client.app.state.llm_resolver.default_client

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Planner must not run for a simple query")

    monkeypatch.setattr(llm, "create_analysis_plan", fail_if_called)
    body = ask(client, "sales", "What is total revenue?")

    assert body["analysis_mode"] == "simple_query"
    assert body["analysis_plan"] is None


def test_planner_contract_and_schema_reject_sql() -> None:
    system_text = str(ANALYSIS_PLAN_PROMPT.messages[0].prompt.template)
    assert "Never output SQL" in system_text
    with pytest.raises(ValidationError):
        AnalysisStep(
            id="step_1",
            question="SELECT SUM(revenue) FROM sales",
            purpose="Run the query",
        )


def test_analysis_plan_has_a_hard_step_limit() -> None:
    step = AnalysisStep(id="step", question="Check the metric.", purpose="Establish a baseline.")
    with pytest.raises(ValidationError):
        AnalysisPlan(
            objective="Investigate a change",
            steps=[step.model_copy(update={"id": f"step_{index}"}) for index in range(6)],
            max_steps=MAX_ANALYSIS_STEPS,
        )


def test_mock_planner_is_deterministic_and_contains_no_sql() -> None:
    llm = MockLLMClient()
    intent = llm.understand_analysis_intent("Why did revenue decline?")

    assert llm.create_analysis_plan("Why did revenue decline?", intent) == llm.create_analysis_plan(
        "Why did revenue decline?", intent
    )
    assert all(
        "select " not in step.question.lower()
        for step in llm.create_analysis_plan("Why did revenue decline?", intent).steps
    )
