from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from app.agent.language import ResponseLanguage


class DataAnalysisState(TypedDict, total=False):
    request_id: str
    run_mode: Literal["interactive", "eval", "test"]
    conversation_id: str | None
    thread_id: str
    dataset_id: str
    dataset_name: str | None
    dataset_db_path: str | None

    question: str
    response_language: ResponseLanguage
    rewritten_question: str | None
    active_analysis_question: str | None
    analysis_mode: Literal["simple_query", "investigative_analysis"]
    analysis_intent: dict[str, Any] | None
    analysis_context: dict[str, Any] | None
    analysis_plan: dict[str, Any] | None
    current_analysis_step_id: str | None
    evidence_by_step: dict[str, dict[str, Any]]
    critic_result: dict[str, Any] | None
    next_analysis_decision: dict[str, Any] | None
    analysis_step_count: int
    evidence_insufficient: bool
    final_analysis: dict[str, Any] | None
    supporting_charts: list[dict[str, Any]]
    tool_failures: int
    decision_retries: int
    conversation_history: list[dict[str, Any]]

    available_tables: list[str]
    dataset_capability: dict[str, Any]
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
    returned_row_count: int
    is_truncated: bool

    chart: dict[str, Any] | None
    insight: str | None
    lineage: dict[str, Any] | None

    repair_attempts: int
    validation_repair_attempts: int
    execution_repair_attempts: int
    repair_source: Literal["validation", "execution"] | None
    grounding_repair_attempts: int
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
