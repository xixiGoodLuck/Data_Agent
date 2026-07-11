from __future__ import annotations

from app.evals.builtin_report import render_builtin_markdown


def test_builtin_report_renders_question_sql_and_failure_reason() -> None:
    report = {
        "run": {
            "id": "run-1",
            "created_at": "2026-07-11T00:00:00Z",
            "passed_cases": 0,
            "total_cases": 1,
            "result_accuracy": 100.0,
            "table_selection_accuracy": 100.0,
            "sql_safety_accuracy": 100.0,
            "dangerous_sql_block_rate": 100.0,
            "chart_selection_accuracy": 0.0,
            "fallback_rate": 0.0,
            "average_latency_ms": 10.0,
        },
        "cases": [
            {
                "id": "case-1",
                "category": "ranking",
                "dataset_id": "sales",
                "question": "Which region leads?",
                "oracle": {"chart_type": "bar"},
                "actual": {"status": "success"},
                "generated_sql": "SELECT region FROM sales LIMIT 1",
                "expected_chart_type": "bar",
                "actual_chart_type": "number",
                "used_fallback": False,
                "latency_ms": 10.0,
                "passed": False,
                "failure_reasons": ["chart"],
            }
        ],
    }

    markdown = render_builtin_markdown(report)

    assert "Which region leads?" in markdown
    assert "SELECT region FROM sales LIMIT 1" in markdown
    assert "失败原因: `chart`" in markdown
