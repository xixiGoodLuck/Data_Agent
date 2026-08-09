from __future__ import annotations

import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.agent.llm import SqlGeneration
from app.schemas.query import (
    AnalysisEvaluation,
    AnalysisPlan,
    AnalysisStep,
    CriticResult,
    NextAnalysisDecision,
)

CASE_A_ROWS = [
    "2026-01,East,Online,Core,A,100,10000",
    "2026-02,East,Online,Core,A,99,8019",
]
CASE_B_ROWS = [
    "2026-01,East,Online,Core,A,100,10000",
    "2026-02,East,Online,Core,A,80,8000",
]


def upload_csv(client: TestClient, name: str, rows: list[str]) -> dict:
    content = (
        "month,region,channel,category,product,orders,revenue\n" + "\n".join(rows) + "\n"
    ).encode()
    response = client.post(
        "/api/datasets/upload",
        files={"file": (f"{name}.csv", content, "text/csv")},
    )
    assert response.status_code == 201
    return response.json()


def upload_xlsx(client: TestClient, name: str, rows: list[str]) -> dict:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Analysis"
    sheet.append(["month", "region", "channel", "category", "product", "orders", "revenue"])
    for row in rows:
        month, region, channel, category, product, orders, revenue = row.split(",")
        sheet.append([month, region, channel, category, product, int(orders), float(revenue)])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    response = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                f"{name}.xlsx",
                output.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 201
    return response.json()


def investigate(client: TestClient, dataset_id: str, request_id: str | None = None) -> dict:
    payload = {"dataset_id": dataset_id, "question": "为什么最近收入下降?"}
    if request_id:
        payload["request_id"] = request_id
    response = client.post("/api/query", json=payload)
    assert response.status_code == 200
    return response.json()


def query_executions(body: dict) -> list[dict]:
    return [event for event in body["trace"] if event["event_type"] == "query_executed"]


def dynamic_step(body: dict) -> str:
    return body["analysis_plan"]["steps"][2]["question"]


def test_simple_query_stays_out_of_agent_loop(client: TestClient) -> None:
    body = client.post(
        "/api/query",
        json={"dataset_id": "commerce", "question": "哪个城市的订单收入最高?"},
    ).json()

    assert body["status"] == "success"
    assert body["analysis_mode"] == "simple_query"
    assert len(query_executions(body)) == 1
    assert body["evidence"] == []
    assert not any(event["event_type"] == "analysis_decision" for event in body["trace"])


def test_case_a_evidence_dynamically_selects_aov_product_path(client: TestClient) -> None:
    dataset = upload_csv(client, "aov-driver", CASE_A_ROWS)
    body = investigate(client, dataset["id"])

    assert body["analysis_mode"] == "investigative_analysis"
    assert len(query_executions(body)) == 3
    assert len(body["evidence"]) == 3
    second = body["evidence"][1]
    assert second["key_values"]["order_count_change_pct"] == -1
    assert second["key_values"]["average_order_value_change_pct"] == -19
    assert "rows" not in second
    assert "产品" in dynamic_step(body)
    assert "平均订单金额" in dynamic_step(body)
    assert body["critic_result"]["sufficient"] is True


def test_case_b_evidence_dynamically_selects_order_region_channel_path(
    client: TestClient,
) -> None:
    dataset = upload_csv(client, "order-driver", CASE_B_ROWS)
    body = investigate(client, dataset["id"])

    second = body["evidence"][1]
    assert second["key_values"]["order_count_change_pct"] == -20
    assert second["key_values"]["average_order_value_change_pct"] == 0
    assert "订单量" in dynamic_step(body)
    assert any(term in dynamic_step(body) for term in ("地区", "渠道"))
    assert len(query_executions(body)) == 3


def test_same_objective_takes_different_third_steps_from_different_evidence(
    client: TestClient,
) -> None:
    case_a = investigate(client, upload_csv(client, "path-a", CASE_A_ROWS)["id"])
    case_b = investigate(client, upload_csv(client, "path-b", CASE_B_ROWS)["id"])

    assert dynamic_step(case_a) != dynamic_step(case_b)
    decisions_a = [event for event in case_a["trace"] if event["event_type"] == "analysis_decision"]
    decisions_b = [event for event in case_b["trace"] if event["event_type"] == "analysis_decision"]
    assert json.loads(decisions_a[1]["output_summary"])["plan_patch"]
    assert json.loads(decisions_b[1]["output_summary"])["plan_patch"]


def test_critic_finishes_early_when_decline_is_not_confirmed(client: TestClient) -> None:
    rows = [
        "2026-01,East,Online,Core,A,100,10000",
        "2026-02,East,Online,Core,A,101,10100",
    ]
    body = investigate(client, upload_csv(client, "no-decline", rows)["id"])

    assert len(query_executions(body)) == 1
    assert body["analysis_step_count"] == 1
    assert body["critic_result"]["sufficient"] is True
    assert body["evidence_insufficient"] is False
    assert body["final_analysis"]["evidence_insufficient"] is False


def test_hard_max_steps_stops_an_insufficient_investigation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = client.app.state.llm_resolver.default_client
    original = llm.create_analysis_plan

    def two_step_plan(question, intent, response_language="en"):
        plan = original(question, intent, response_language)
        return AnalysisPlan(
            objective=plan.objective,
            steps=plan.steps[:2],
            max_steps=2,
            status="pending",
        )

    monkeypatch.setattr(llm, "create_analysis_plan", two_step_plan)
    body = investigate(client, upload_csv(client, "bounded", CASE_A_ROWS)["id"])

    assert len(query_executions(body)) == 2
    assert body["analysis_step_count"] == 2
    assert body["evidence_insufficient"] is True
    assert body["critic_result"]["sufficient"] is False
    assert body["final_analysis"]["evidence_insufficient"] is True


def test_every_agent_step_reuses_validator_and_unsafe_sql_is_blocked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = client.app.state.llm_resolver.default_client

    def unsafe_sql(*_args, **_kwargs):
        return SqlGeneration(sql="DROP TABLE sales", explanation="Unsafe test output")

    monkeypatch.setattr(llm, "generate_sql", unsafe_sql)
    body = investigate(client, "sales")

    assert body["status"] == "blocked"
    assert body["evidence"] == []
    assert len(query_executions(body)) == 0
    assert any(
        event["node_name"] == "validate_sql_node" and event["event_type"] == "sql_blocked"
        for event in body["trace"]
    )


def test_repair_loop_remains_inside_each_query_tool_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = client.app.state.llm_resolver.default_client
    original = llm.generate_sql
    calls = 0

    def repair_first_step(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SqlGeneration(
                sql=(
                    "SELECT DATE_TRUNC('month', order_date) AS month, "
                    "SUM(revenue) AS total_revenue FROM sales GROUP BY 1 ORDER BY 1"
                ),
                explanation="Repair test",
                selected_columns=["sales.order_date", "sales.revenue"],
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(llm, "generate_sql", repair_first_step)
    body = investigate(client, "sales")

    assert body["status"] == "success"
    assert len(body["evidence"]) >= 2
    assert any(event["node_name"] == "repair_sql_node" for event in body["trace"])


def test_approval_resume_preserves_prior_evidence_and_continues_loop(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = client.app.state.llm_resolver.default_client

    def approval_plan(_question, intent, _response_language="en"):
        return AnalysisPlan(
            objective=intent.objective,
            steps=[
                AnalysisStep(
                    id="step_1",
                    question="Compare average performance by department.",
                    purpose="Create a safe baseline.",
                ),
                AnalysisStep(
                    id="step_2",
                    question="Show headcount by department.",
                    purpose="Measure workforce volume safely.",
                ),
                AnalysisStep(
                    id="step_3",
                    question="Identify the next workforce driver.",
                    purpose="Use prior evidence to choose a sensitive follow-up.",
                ),
            ],
            max_steps=5,
        )

    def approval_evaluation(_intent, plan, evidence, _response_language="en"):
        if len(evidence) == 1:
            next_step = next(step for step in plan.steps if step.id == "step_2")
        elif len(evidence) == 2:
            next_step = AnalysisStep(
                id="step_3",
                question="List employee names and individual salary values.",
                purpose="Inspect the sensitive driver after aggregate evidence.",
            )
        elif len(evidence) == 3:
            next_step = AnalysisStep(
                id="step_4",
                question="Show headcount by location.",
                purpose="Continue with a safe aggregate after approval.",
            )
        else:
            return AnalysisEvaluation(
                critic=CriticResult(sufficient=True, answered_objective=True),
                decision=NextAnalysisDecision(
                    action="finish",
                    reason="The resumed investigation collected the required evidence.",
                ),
            )
        return AnalysisEvaluation(
            critic=CriticResult(
                sufficient=False,
                answered_objective=False,
                missing_evidence=[next_step.purpose],
                recommended_next_step=next_step.question,
            ),
            decision=NextAnalysisDecision(
                action="continue",
                next_step=next_step,
                reason="The current aggregate evidence identifies a specific next check.",
                plan_patch={"source_step_count": len(evidence)},
            ),
        )

    monkeypatch.setattr(llm, "create_analysis_plan", approval_plan)
    monkeypatch.setattr(llm, "evaluate_analysis", approval_evaluation)
    pending = client.post(
        "/api/query",
        json={
            "dataset_id": "employees",
            "question": "Why did workforce performance decline?",
            "request_id": "approval-agent-loop",
        },
    ).json()

    assert pending["status"] == "pending_approval"
    assert len(pending["evidence"]) == 2
    assert len(query_executions(pending)) == 2
    prior_evidence_ids = [item["id"] for item in pending["evidence"]]
    prior_step_ids = [step["id"] for step in pending["analysis_plan"]["steps"]]

    resumed = client.post(
        f"/api/approvals/{pending['approval']['id']}/approve",
        json={"note": "Approved for deterministic test"},
    )
    assert resumed.status_code == 200
    body = resumed.json()

    assert body["status"] == "success"
    assert len(query_executions(body)) == 4
    assert len(body["evidence"]) == 4
    assert [item["id"] for item in body["evidence"][:2]] == prior_evidence_ids
    assert len({item["id"] for item in body["evidence"]}) == 4
    assert [step["id"] for step in body["analysis_plan"]["steps"][:3]] == prior_step_ids
    assert body["analysis_plan"]["steps"][3]["id"] == "step_4"
    assert body["final_analysis"] is not None
    assert body["final_analysis"]["evidence_ids"] == [item["id"] for item in body["evidence"]]


def test_csv_investigative_analysis_uses_multi_step_agent(client: TestClient) -> None:
    body = investigate(client, upload_csv(client, "csv-agent", CASE_A_ROWS)["id"])

    assert body["analysis_mode"] == "investigative_analysis"
    assert len(body["evidence"]) >= 2
    assert len(query_executions(body)) >= 2
    assert body["final_analysis"] is not None


def test_xlsx_dataset_runs_through_multi_step_agent(client: TestClient) -> None:
    dataset = upload_xlsx(client, "xlsx-agent", CASE_B_ROWS)
    body = investigate(client, dataset["id"])

    assert dataset["source_type"] == "excel_upload"
    assert body["analysis_mode"] == "investigative_analysis"
    assert body["analysis_plan"] is not None
    assert len(body["evidence"]) >= 2
    assert len(query_executions(body)) >= 2
    assert body["final_analysis"] is not None
    assert body["supporting_charts"]
