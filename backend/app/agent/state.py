from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


class DataAnalysisState(TypedDict, total=False):
    request_id: str
    run_mode: Literal["interactive", "eval", "test"]
    conversation_id: str | None
    thread_id: str
    dataset_id: str
    dataset_name: str | None
    dataset_db_path: str | None

    question: str
    rewritten_question: str | None
    conversation_history: list[dict[str, Any]]

    available_tables: list[str]
    selected_tables: list[str]
    selected_columns: list[str]
    dataset_schema: dict[str, Any]
    schema_context: str | None
    schema_hash: str | None

    generated_sql: str | None
    sql_explanation: str | None
    normalized_sql: str | None
    safe_sql: bool
    safety_reason: str | None

    risk_level: Literal["low", "medium", "high"]
    risk_reasons: list[str]
    requires_approval: bool
    approval_id: str | None
    approval_decision: dict[str, Any] | None

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int

    chart: dict[str, Any] | None
    insight: str | None
    lineage: dict[str, Any] | None

    repair_attempts: int
    used_fallback: bool
    llm_provider: str
    execution_outcome: str | None
    execution_error: dict[str, Any] | None
    clarification_question: str | None
    started_at_epoch_ms: float

    query_log_id: str | None
    run_id: str | None
    status: str
    final_response: dict[str, Any] | None

    events: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[dict[str, Any]], operator.add]
