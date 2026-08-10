from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.analysis import build_evidence
from app.agent.llm import MockLLMClient
from app.agent.nodes import AnalysisNodes
from app.agent.prompts import ANALYSIS_PLAN_PROMPT, SQL_GENERATION_PROMPT, TABLE_SELECTION_PROMPT
from app.schemas.query import (
    MAX_ANALYSIS_STEPS,
    AnalysisEvaluation,
    AnalysisIntent,
    AnalysisPlan,
    AnalysisStep,
    CriticResult,
    Evidence,
    NextAnalysisDecision,
)


def ask(client: TestClient, dataset_id: str, question: str) -> dict:
    response = client.post(
        "/api/query",
        json={"dataset_id": dataset_id, "question": question},
    )
    assert response.status_code == 200
    return response.json()


def test_evidence_preserves_first_and_last_dimension_values() -> None:
    result = build_evidence(
        {
            "request_id": "dimension-boundaries",
            "current_analysis_step_id": "step1",
            "active_analysis_question": "Show the monthly trend.",
            "normalized_sql": "SELECT month, revenue FROM data ORDER BY month",
            "response_language": "en",
            "dataset_schema": {},
            "columns": ["month", "revenue"],
            "rows": [
                {"month": "2024-01", "revenue": 100},
                {"month": "2025-12", "revenue": 80},
            ],
            "row_count": 2,
        }
    )

    assert result.key_values["first_month"] == "2024-01"
    assert result.key_values["last_month"] == "2025-12"


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


def test_table_selection_accepts_safely_derived_metrics() -> None:
    system_text = str(TABLE_SELECTION_PROMPT.messages[0].prompt.template)
    assert "derived from available columns" in system_text
    assert "optional example dimension is absent" in system_text
    assert "do not require a precomputed column" in system_text


def test_sql_generation_prefers_aggregates_for_investigations() -> None:
    system_text = str(SQL_GENERATION_PROMPT.messages[0].prompt.template)
    assert "instead of returning broad row-level data" in system_text


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


def test_prepare_analysis_step_honors_dynamic_next_step(client: TestClient, test_settings) -> None:
    nodes = AnalysisNodes(
        settings=test_settings,
        metadata=client.app.state.metadata,
        llm=client.app.state.llm_resolver,
    )
    plan = AnalysisPlan(
        objective="Explain the revenue decline",
        steps=[
            AnalysisStep(
                id="step_1",
                question="Confirm the decline.",
                purpose="Establish the trend.",
                status="completed",
            ),
            AnalysisStep(
                id="step_4",
                question="Inspect price changes.",
                purpose="Test the price hypothesis.",
            ),
            AnalysisStep(
                id="step_5",
                question="Inspect order-volume drivers.",
                purpose="Test the volume hypothesis.",
            ),
        ],
        max_steps=5,
        status="running",
    )
    result = nodes.prepare_analysis_step_node(
        {
            "request_id": "dynamic-next-step",
            "question": "Why did revenue decline?",
            "analysis_plan": plan.model_dump(),
            "next_analysis_decision": {
                "action": "continue",
                "next_step": plan.steps[2].model_dump(),
                "reason": "Skip the disproven price hypothesis.",
            },
            "events": [],
        }
    )

    assert result["current_analysis_step_id"] == "step_5"
    assert result["active_analysis_question"] == "Inspect order-volume drivers."
    updated = AnalysisPlan.model_validate(result["analysis_plan"])
    assert next(step for step in updated.steps if step.id == "step_4").status == "pending"
    assert next(step for step in updated.steps if step.id == "step_5").status == "running"


def test_dynamic_next_step_replaces_pending_slot_when_plan_is_full(
    client: TestClient, test_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    nodes = AnalysisNodes(
        settings=test_settings,
        metadata=client.app.state.metadata,
        llm=client.app.state.llm_resolver,
    )
    plan = AnalysisPlan(
        objective="Explain the revenue decline",
        steps=[
            AnalysisStep(
                id=f"step{index}",
                question=f"Analyze driver {index}.",
                purpose=f"Test driver {index}.",
                status="completed" if index == 1 else "pending",
            )
            for index in range(1, 6)
        ],
        max_steps=5,
        status="running",
    )
    dynamic = AnalysisStep(
        id="step_3",
        question="Resolve the conflicting monthly evidence.",
        purpose="Use a bounded replacement step.",
    )
    monkeypatch.setattr(
        client.app.state.llm_resolver.default_client,
        "evaluate_analysis",
        lambda *_args, **_kwargs: AnalysisEvaluation(
            critic=CriticResult(
                sufficient=False,
                answered_objective=False,
                missing_evidence=[dynamic.purpose],
            ),
            decision=NextAnalysisDecision(
                action="continue",
                next_step=dynamic,
                reason="The original pending step no longer matches the evidence.",
            ),
        ),
    )
    result = nodes.evaluate_analysis_node(
        {
            "request_id": "dynamic-full-plan",
            "question": "Why did revenue decline?",
            "response_language": "en",
            "analysis_intent": AnalysisIntent(
                objective="Explain the decline",
                analysis_type="diagnostic",
                needs_multi_step=True,
                reason="Requires multiple checks.",
            ).model_dump(),
            "analysis_plan": plan.model_dump(),
            "evidence_by_step": {
                "step1": Evidence(
                    id="evidence-1",
                    step_id="step1",
                    question="Analyze driver 1.",
                    sql="SELECT 1",
                    result_summary="The baseline is established.",
                    row_count=1,
                    created_at=datetime.now(UTC),
                ).model_dump()
            },
            "analysis_step_count": 1,
            "events": [],
        }
    )

    updated = AnalysisPlan.model_validate(result["analysis_plan"])
    assert len(updated.steps) == 5
    assert updated.steps[1] == dynamic
    assert result["next_analysis_decision"]["action"] == "continue"
