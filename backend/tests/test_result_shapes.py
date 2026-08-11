from __future__ import annotations

import random
import sqlite3
from pathlib import Path

import pytest

from app.agent.analysis import build_dataset_capability, build_evidence
from app.agent.llm import MockLLMClient
from app.schemas.query import AnalysisIntent, AnalysisPlan, AnalysisStep
from app.sql.executor import execute_read_only


def evidence_state(
    *,
    question: str,
    sql: str,
    columns: list[str],
    rows: list[dict],
    **extra,
) -> dict:
    return {
        "request_id": "shape-test",
        "current_analysis_step_id": "step_1",
        "active_analysis_question": question,
        "normalized_sql": sql,
        "response_language": "en",
        "dataset_schema": {},
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "returned_row_count": len(rows),
        **extra,
    }


def test_time_series_generates_period_change() -> None:
    evidence = build_evidence(
        evidence_state(
            question="Show the monthly revenue trend.",
            sql="SELECT month, revenue FROM data ORDER BY month",
            columns=["month", "revenue"],
            rows=[
                {"month": "2026-06", "revenue": 100},
                {"month": "2026-07", "revenue": 80},
            ],
        )
    )

    assert evidence.result_shape == "time_series"
    assert evidence.key_values["previous_revenue"] == 100
    assert evidence.key_values["current_revenue"] == 80
    assert evidence.key_values["revenue_change_pct"] == -20


def test_multi_series_time_changes_are_isolated_and_order_independent() -> None:
    rows = [
        {"month": "2025-02", "region": "West", "revenue": 80},
        {"month": "2025-01", "region": "East", "revenue": 100},
        {"month": "2025-01", "region": "West", "revenue": 40},
        {"month": "2025-02", "region": "East", "revenue": 110},
    ]
    expected = {
        "East": {"previous_revenue": 100.0, "current_revenue": 110.0, "revenue_change_pct": 10.0},
        "West": {"previous_revenue": 40.0, "current_revenue": 80.0, "revenue_change_pct": 100.0},
    }

    for seed in range(5):
        shuffled = rows.copy()
        random.Random(seed).shuffle(shuffled)
        evidence = build_evidence(
            evidence_state(
                question="Compare the monthly revenue trend by region.",
                sql="SELECT month, region, revenue FROM data",
                columns=["month", "region", "revenue"],
                rows=shuffled,
            )
        )
        assert evidence.result_shape_metadata is not None
        assert evidence.result_shape_metadata.time_column == "month"
        assert evidence.result_shape_metadata.series_columns == ["region"]
        assert evidence.series_changes == expected
        assert "previous_revenue" not in evidence.key_values


@pytest.mark.parametrize("series_column", ["channel", "category"])
def test_multi_series_time_changes_support_business_dimensions(series_column: str) -> None:
    evidence = build_evidence(
        evidence_state(
            question="Compare monthly metrics by series.",
            sql=f"SELECT month, {series_column}, revenue, quantity FROM data",
            columns=["month", series_column, "revenue", "quantity"],
            rows=[
                {"month": "2025-01", series_column: "A", "revenue": 100, "quantity": 10},
                {"month": "2025-02", series_column: "A", "revenue": 75, "quantity": 15},
            ],
        )
    )

    assert evidence.series_changes["A"]["revenue_change_pct"] == -25
    assert evidence.series_changes["A"]["quantity_change_pct"] == 50
    assert {fact.dimension_value for fact in evidence.facts if fact.dimension} == {"A"}


def test_categorical_breakdown_never_generates_period_change() -> None:
    evidence = build_evidence(
        evidence_state(
            question="Compare revenue by category.",
            sql="SELECT category, SUM(revenue) AS revenue FROM data GROUP BY category",
            columns=["category", "revenue"],
            rows=[
                {"category": "B", "revenue": 80},
                {"category": "A", "revenue": 100},
            ],
        )
    )

    assert evidence.result_shape == "categorical_breakdown"
    assert evidence.key_values["top_dimension"] == "A"
    assert evidence.key_values["top_metric"] == 100
    assert not any(
        key.startswith(("previous_", "current_")) or key.endswith("_change_pct")
        for key in evidence.key_values
    )
    assert "changed" not in evidence.result_summary.lower()


def test_ranking_uses_first_ranked_value() -> None:
    evidence = build_evidence(
        evidence_state(
            question="Rank categories by revenue.",
            sql=(
                "SELECT category, SUM(revenue) AS revenue FROM data "
                "GROUP BY category ORDER BY revenue DESC"
            ),
            columns=["category", "revenue"],
            rows=[
                {"category": "A", "revenue": 100},
                {"category": "B", "revenue": 80},
            ],
        )
    )

    assert evidence.result_shape == "ranking"
    assert evidence.key_values["top_dimension"] == "A"
    assert evidence.key_values["top_metric"] == 100
    assert evidence.key_values["bottom_dimension"] == "B"


def test_categorical_evidence_does_not_make_critic_claim_a_period_decline() -> None:
    client = MockLLMClient()
    intent = AnalysisIntent(
        objective="Explain why the metric declined.",
        analysis_type="diagnostic",
        metrics=["revenue"],
        needs_multi_step=True,
        reason="Evidence-guided diagnosis is required.",
    )
    plan = AnalysisPlan(
        objective=intent.objective,
        steps=[
            AnalysisStep(id="step_1", question="Compare categories.", purpose="Find variation."),
            AnalysisStep(id="step_2", question="Inspect another dimension.", purpose="Continue."),
        ],
    )
    evidence = build_evidence(
        evidence_state(
            question="Compare categories.",
            sql="SELECT category, SUM(revenue) revenue FROM data GROUP BY category",
            columns=["category", "revenue"],
            rows=[{"category": "A", "revenue": 100}, {"category": "B", "revenue": 80}],
        )
    )

    evaluation = client.evaluate_analysis(intent, plan, [evidence])

    assert evaluation.decision.action == "continue"
    assert evaluation.critic.sufficient is False
    assert "revenue_change_pct" not in evidence.key_values


def test_dataset_capability_changes_the_plan_without_sample_rows() -> None:
    client = MockLLMClient()
    intent = AnalysisIntent(
        objective="Why did the metric decline?",
        analysis_type="diagnostic",
        metrics=[],
        needs_multi_step=True,
        reason="Evidence-guided diagnosis is required.",
    )
    sales_capability = build_dataset_capability(
        {
            "sales": {
                "columns": [
                    {"name": "date", "type": "TEXT"},
                    {"name": "revenue", "type": "REAL"},
                    {"name": "quantity", "type": "INTEGER"},
                    {"name": "region", "type": "TEXT"},
                ],
                "foreign_keys": [],
            }
        }
    )
    conversion_capability = build_dataset_capability(
        {
            "traffic": {
                "columns": [
                    {"name": "date", "type": "TEXT"},
                    {"name": "conversion_rate", "type": "REAL"},
                    {"name": "traffic", "type": "INTEGER"},
                    {"name": "device", "type": "TEXT"},
                    {"name": "source", "type": "TEXT"},
                ],
                "foreign_keys": [],
            }
        }
    )

    sales_plan = client.create_analysis_plan(intent.objective, intent, "en", sales_capability)
    conversion_plan = client.create_analysis_plan(
        intent.objective, intent, "en", conversion_capability
    )

    assert sales_plan != conversion_plan
    assert "revenue" in " ".join(step.question for step in sales_plan.steps)
    conversion_questions = " ".join(step.question for step in conversion_plan.steps)
    assert "conversion rate" in conversion_questions
    assert "device" in conversion_questions
    assert all(
        "sample_rows" not in capability for capability in (sales_capability, conversion_capability)
    )


def test_dataset_capability_does_not_treat_foreign_keys_as_metrics() -> None:
    capability = build_dataset_capability(
        {
            "orders": {
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "customer_id", "type": "INTEGER", "primary_key": False},
                    {"name": "revenue", "type": "REAL", "primary_key": False},
                ],
                "foreign_keys": [
                    {"from_column": "customer_id", "to_table": "customers", "to_column": "id"}
                ],
            }
        }
    )

    assert capability["metrics"] == ["revenue"]
    assert "customer_id" not in capability["dimensions"]


def test_executor_and_evidence_report_truncation(tmp_path: Path) -> None:
    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()
    db_path = datasets_dir / "data.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, value REAL)")
        connection.executemany("INSERT INTO data(value) VALUES (?)", [(1,), (2,), (3,)])
    result = execute_read_only(
        db_path=db_path,
        sql="SELECT id, value FROM data ORDER BY id",
        datasets_dir=datasets_dir,
        metadata_paths=set(),
        max_rows=2,
    )

    assert result.success is True
    assert result.row_count == 2
    assert result.returned_row_count == 2
    assert result.is_truncated is True

    evidence = build_evidence(
        evidence_state(
            question="List values.",
            sql="SELECT id, value FROM data ORDER BY id",
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
            returned_row_count=result.returned_row_count,
            is_truncated=result.is_truncated,
        )
    )
    assert evidence.is_truncated is True
    assert "first 2 rows" in evidence.limitations[0]
