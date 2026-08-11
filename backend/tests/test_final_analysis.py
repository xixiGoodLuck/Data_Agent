from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.agent.grounding import validate_final_analysis
from app.core.errors import AppError
from app.evals.investigative import INVESTIGATIVE_EVAL_CASES, score_investigative_response
from app.schemas.query import Evidence, EvidenceFact, FinalAnalysis, Finding


def evidence() -> Evidence:
    return Evidence(
        id="evidence-1",
        step_id="step_1",
        question="Compare revenue periods.",
        sql="SELECT 1",
        result_summary="Revenue changed by -20%.",
        key_values={"revenue_change_pct": -20.0},
        row_count=2,
        lineage={"tables": ["sales"], "columns": ["revenue"], "schema_hash": "hash"},
        limitations=["External market variables are not present."],
        created_at=datetime.now(UTC),
    )


def analysis(statement: str = "Revenue changed by -20%.") -> FinalAnalysis:
    return FinalAnalysis(
        executive_summary="Revenue declined in the observed data.",
        key_findings=[
            Finding(
                statement=statement,
                evidence_ids=["evidence-1"],
                facts={"revenue_change_pct": -20.0},
            )
        ],
        limitations=["External market variables are not present."],
        recommended_actions=["Review the affected product categories."],
        evidence_ids=["evidence-1"],
    )


def test_final_analysis_accepts_structured_grounded_output() -> None:
    assert validate_final_analysis(analysis(), [evidence()], evidence_insufficient=False)


def test_final_analysis_can_ground_exact_evidence_fact_ids() -> None:
    item = evidence().model_copy(
        update={
            "facts": [
                EvidenceFact(
                    fact_id="evidence-1:revenue_change_pct",
                    metric="revenue_change_pct",
                    statistic="change_pct",
                    value=-20.0,
                    unit="percent",
                )
            ]
        }
    )
    grounded = analysis()
    grounded.key_findings[0].fact_ids = ["evidence-1:revenue_change_pct"]

    assert validate_final_analysis(grounded, [item], evidence_insufficient=False)


def test_final_analysis_rejects_unknown_evidence_fact_id() -> None:
    grounded = analysis()
    grounded.key_findings[0].fact_ids = ["evidence-1:missing"]

    with pytest.raises(AppError, match="fact"):
        validate_final_analysis(grounded, [evidence()], evidence_insufficient=False)


def test_grounding_accepts_thousands_separators_and_reasonable_rounding() -> None:
    item = evidence().model_copy(
        update={
            "result_summary": "Revenue was 25,866.00 after previously being 26,245.81.",
            "key_values": {
                "current_revenue": 25866.0,
                "previous_revenue": 26245.81,
                "revenue_change_pct": -1.4471,
            },
        }
    )
    grounded = FinalAnalysis(
        executive_summary="Revenue declined by 1.45%, from 26,245.81 to 25,866.00.",
        key_findings=[],
        evidence_ids=[item.id],
    )

    assert validate_final_analysis(grounded, [item], evidence_insufficient=False)


def test_invalid_evidence_id_is_rejected() -> None:
    invalid = analysis().model_copy(deep=True)
    invalid.key_findings[0].evidence_ids = ["evidence-999"]
    with pytest.raises(AppError, match="does not exist"):
        validate_final_analysis(invalid, [evidence()], evidence_insufficient=False)


def test_hallucinated_numeric_fact_is_rejected() -> None:
    with pytest.raises(AppError, match="numeric finding"):
        validate_final_analysis(
            analysis("Revenue changed by -30%."), [evidence()], evidence_insufficient=False
        )


def test_hallucinated_numeric_executive_summary_is_rejected() -> None:
    invalid = analysis().model_copy(update={"executive_summary": "Revenue declined by -30%."})
    with pytest.raises(AppError, match="numeric finding"):
        validate_final_analysis(invalid, [evidence()], evidence_insufficient=False)


def test_grounding_accepts_period_numbers_from_structured_evidence() -> None:
    dated_evidence = evidence().model_copy(
        update={"key_values": {"revenue_2025_02": 210000.0, "top_month": "2025-02"}}
    )
    dated_analysis = analysis("Revenue in 2025-02 was 210000.").model_copy(
        update={"executive_summary": "Revenue in 2025-02 was 210000."}
    )
    dated_analysis.key_findings[0].facts = {"revenue_2025_02": 210000.0}

    assert validate_final_analysis(dated_analysis, [dated_evidence], evidence_insufficient=False)


def test_grounding_accepts_unsigned_decline_magnitude() -> None:
    declined = analysis("Revenue declined 20%.")

    assert validate_final_analysis(declined, [evidence()], evidence_insufficient=False)


def test_grounding_rejects_unsigned_increase_for_negative_evidence() -> None:
    invalid = analysis("Revenue increased 20%.")
    with pytest.raises(AppError, match="numeric finding"):
        validate_final_analysis(invalid, [evidence()], evidence_insufficient=False)


def test_grounding_reads_numbers_adjacent_to_chinese_text() -> None:
    chinese = analysis("收入下降20.0%。")

    assert validate_final_analysis(chinese, [evidence()], evidence_insufficient=False)


def test_grounding_accepts_executed_sql_date_literals() -> None:
    dated_evidence = evidence().model_copy(
        update={
            "sql": "SELECT SUM(revenue) FROM sales WHERE month = '2024-11'",
            "key_values": {"revenue_change_pct": 8.26},
        }
    )
    dated = analysis("Revenue increased 8.26% in 2024-11.").model_copy(
        update={"executive_summary": "Revenue increased 8.26% in 2024-11."}
    )
    dated.key_findings[0].facts = {"revenue_change_pct": 8.26}

    assert validate_final_analysis(dated, [dated_evidence], evidence_insufficient=False)


def test_grounding_accepts_period_length_derived_from_sql_boundaries() -> None:
    period_evidence = evidence().model_copy(
        update={
            "sql": (
                "SELECT SUM(revenue) FROM sales "
                "WHERE month >= '2025-07-01' AND month < '2026-01-01'"
            )
        }
    )
    period = analysis("Revenue declined 20% over 6 months.")

    assert validate_final_analysis(period, [period_evidence], evidence_insufficient=False)


def test_grounding_ignores_numbers_in_step_identifiers() -> None:
    step_reference = analysis("Step_2 confirms revenue declined 20%.")

    assert validate_final_analysis(step_reference, [evidence()], evidence_insufficient=False)


def test_grounding_accepts_percentage_rate_conversion() -> None:
    rate_evidence = evidence().model_copy(
        update={"key_values": {"revenue_change_rate_min": -0.1305}}
    )
    converted = analysis("Revenue declined 13.05%.")
    converted.key_findings[0].facts = {"revenue_change_rate": -0.1305}

    assert validate_final_analysis(converted, [rate_evidence], evidence_insufficient=False)


def test_grounding_accepts_percentage_threshold_executed_in_sql() -> None:
    threshold_evidence = evidence().model_copy(
        update={
            "sql": "SELECT CASE WHEN discount < 0.3 THEN 'under' ELSE 'high' END FROM items",
            "key_values": {"discount_max": 0.15},
            "row_count": 4,
        }
    )
    threshold_analysis = analysis("No observed group reached the 30% threshold.")
    threshold_analysis.key_findings[0].facts = {}

    assert validate_final_analysis(
        threshold_analysis, [threshold_evidence], evidence_insufficient=False
    )


def test_grounding_still_rejects_unexecuted_percentage_threshold() -> None:
    threshold_evidence = evidence().model_copy(
        update={
            "sql": "SELECT CASE WHEN discount < 0.3 THEN 'under' ELSE 'high' END FROM items",
            "key_values": {"discount_max": 0.15},
            "row_count": 4,
        }
    )
    threshold_analysis = analysis("No observed group reached the 45% threshold.")
    threshold_analysis.key_findings[0].facts = {}

    with pytest.raises(AppError, match="numeric finding"):
        validate_final_analysis(
            threshold_analysis, [threshold_evidence], evidence_insufficient=False
        )


def test_grounding_accepts_threshold_from_cited_evidence_question() -> None:
    threshold_evidence = evidence().model_copy(
        update={
            "question": "Check whether values reach 0.2 or 0.3.",
            "sql": "SELECT discount FROM items ORDER BY discount",
            "key_values": {"discount_max": 0.15},
            "row_count": 4,
        }
    )
    threshold_analysis = analysis("The observed values do not reach 0.3.")
    threshold_analysis.key_findings[0].facts = {}

    assert validate_final_analysis(
        threshold_analysis, [threshold_evidence], evidence_insufficient=False
    )


def test_grounding_accepts_simple_calculation_from_cited_values() -> None:
    calculated_evidence = evidence().model_copy(
        update={"key_values": {"orders": 68, "average_order_value": 1260.67}}
    )
    calculated = analysis("Estimated revenue was about 85725.56.")
    calculated.key_findings[0].facts = {}

    assert validate_final_analysis(calculated, [calculated_evidence], evidence_insufficient=False)


def test_grounding_accepts_fact_backed_by_min_max_summary_key() -> None:
    summarized = evidence().model_copy(update={"key_values": {"pct_change_max": 8.26}})
    summarized_analysis = analysis("Revenue increased 8.26%.")
    summarized_analysis.key_findings[0].facts = {"pct_change": 8.26}

    assert validate_final_analysis(summarized_analysis, [summarized], evidence_insufficient=False)


def test_unsupported_marketing_cause_is_rejected() -> None:
    unsupported = analysis("Marketing spend reductions caused the -20% revenue change.")
    with pytest.raises(AppError, match="absent from the evidence"):
        validate_final_analysis(unsupported, [evidence()], evidence_insufficient=False)


def test_missing_marketing_data_is_a_valid_limitation() -> None:
    limited = analysis("Revenue declined 20%. Marketing data is missing, so the cause is unknown.")

    assert validate_final_analysis(limited, [evidence()], evidence_insufficient=False)


def test_evidence_insufficient_cannot_be_cleared() -> None:
    with pytest.raises(AppError, match="cannot clear"):
        validate_final_analysis(analysis(), [evidence()], evidence_insufficient=True)


def test_simple_query_does_not_enter_final_synthesis(client: TestClient) -> None:
    body = client.post(
        "/api/query",
        json={"dataset_id": "commerce", "question": "Which city has the highest revenue?"},
    ).json()
    assert body["analysis_mode"] == "simple_query"
    assert body["final_analysis"] is None
    assert body["supporting_charts"] == []
    assert sum(event["event_type"] == "query_executed" for event in body["trace"]) == 1


def test_investigation_is_synthesized_grounded_and_charted(client: TestClient) -> None:
    body = client.post(
        "/api/query", json={"dataset_id": "sales", "question": "Why did revenue decline?"}
    ).json()
    assert body["status"] == "success"
    assert body["final_analysis"]
    assert body["final_analysis"]["evidence_ids"]
    known_ids = {item["id"] for item in body["evidence"]}
    assert all(
        set(finding["evidence_ids"]).issubset(known_ids)
        for finding in body["final_analysis"]["key_findings"]
    )
    assert 1 <= len(body["supporting_charts"]) <= 3
    assert any(event["event_type"] == "final_grounding_validated" for event in body["trace"])


def test_grounding_failure_repairs_final_synthesis_once_without_rerunning_sql(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = client.app.state.llm_resolver.default_client
    calls: list[str | None] = []

    def synthesize(
        _question,
        _intent,
        _plan,
        evidence_items,
        _critic,
        evidence_insufficient,
        _response_language="en",
        grounding_feedback=None,
    ):
        calls.append(grounding_feedback)
        if grounding_feedback is None:
            return FinalAnalysis(
                executive_summary="The unsupported result is 999999.",
                evidence_ids=[item.id for item in evidence_items],
                evidence_insufficient=evidence_insufficient,
            )
        return FinalAnalysis(
            executive_summary="The supplied evidence supports the bounded findings.",
            evidence_ids=[item.id for item in evidence_items],
            evidence_insufficient=evidence_insufficient,
        )

    monkeypatch.setattr(llm, "synthesize_analysis", synthesize)
    body = client.post(
        "/api/query", json={"dataset_id": "sales", "question": "Why did revenue decline?"}
    ).json()

    assert body["status"] == "success"
    assert len(calls) == 2
    assert calls[0] is None
    assert calls[1] and "final_analysis_grounding_error" in calls[1]
    assert sum(event["event_type"] == "final_synthesis_started" for event in body["trace"]) == 1
    assert sum(event["event_type"] == "query_executed" for event in body["trace"]) == len(
        body["evidence"]
    )


def test_grounding_failure_stops_after_one_failed_repair(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = client.app.state.llm_resolver.default_client
    calls = 0

    def invalid_synthesis(
        _question,
        _intent,
        _plan,
        evidence_items,
        _critic,
        evidence_insufficient,
        _response_language="en",
        _grounding_feedback=None,
    ):
        nonlocal calls
        calls += 1
        return FinalAnalysis(
            executive_summary="The unsupported result is 999999.",
            evidence_ids=[item.id for item in evidence_items],
            evidence_insufficient=evidence_insufficient,
        )

    monkeypatch.setattr(llm, "synthesize_analysis", invalid_synthesis)
    body = client.post(
        "/api/query", json={"dataset_id": "sales", "question": "Why did revenue decline?"}
    ).json()

    assert body["status"] == "failed"
    assert body["error"]["type"] == "final_analysis_grounding_error"
    assert calls == 2
    assert any(event["event_type"] == "final_grounding_failed" for event in body["trace"])


def test_conversation_reopen_restores_full_analysis(client: TestClient) -> None:
    body = client.post(
        "/api/query", json={"dataset_id": "sales", "question": "Why did revenue decline?"}
    ).json()
    reopened = client.get(f"/api/conversations/{body['conversation_id']}").json()
    assistant = next(message for message in reopened["messages"] if message["role"] == "assistant")
    assert assistant["result"]["analysis_plan"] == body["analysis_plan"]
    assert assistant["result"]["evidence"] == body["evidence"]
    assert assistant["result"]["final_analysis"] == body["final_analysis"]


def test_investigative_eval_defines_eight_grounding_oriented_cases(client: TestClient) -> None:
    assert len(INVESTIGATIVE_EVAL_CASES) == 8
    body = client.post(
        "/api/query", json={"dataset_id": "sales", "question": "Why did revenue decline?"}
    ).json()
    checks = score_investigative_response(INVESTIGATIVE_EVAL_CASES[0], body)
    assert checks["analysis_mode"]
    assert checks["evidence_unique"]
    assert checks["grounded_findings"]
