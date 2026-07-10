from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.evals.runner import load_eval_cases
from app.models import EvalCaseResult, EvalRun


def test_eval_dataset_contains_at_least_thirty_meaningful_cases() -> None:
    cases = load_eval_cases()
    assert len(cases) >= 30
    categories = {case.category for case in cases}
    assert {
        "multi_table_aggregation",
        "dangerous_sql",
        "sensitive_approval",
        "clarification",
        "sql_repair",
        "follow_up",
    }.issubset(categories)


def test_eval_runs_actual_graph_persists_metrics_and_does_not_pollute_stats(
    client: TestClient, metadata
) -> None:
    response = client.post("/api/evals/run")
    assert response.status_code == 200
    run = response.json()
    assert run["total_cases"] >= 30
    assert run["passed_cases"] == run["total_cases"]
    assert run["dangerous_sql_block_rate"] == 100
    assert run["approval_accuracy"] == 100
    assert run["repair_success_rate"] == 100
    assert len(run["cases"]) == run["total_cases"]
    assert all("expected" in case and "actual" in case for case in run["cases"])
    with metadata.session() as session:
        assert session.scalar(select(func.count(EvalRun.id))) == 1
        assert session.scalar(select(func.count(EvalCaseResult.id))) == run["total_cases"]
    assert client.get("/api/stats/overview").json()["total_queries"] == 0
    assert client.get("/api/evals/latest").json()["id"] == run["id"]
    assert client.get(f"/api/evals/{run['id']}").status_code == 200
