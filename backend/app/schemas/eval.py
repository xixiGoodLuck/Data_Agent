from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EvalCaseResponse(BaseModel):
    id: str
    case_id: str
    category: str
    passed: bool
    status: str
    generated_sql: str | None
    actual_tables: list[str]
    actual_chart_type: str | None
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)
    failure_reasons: list[str]
    latency_ms: float


class EvalRunResponse(BaseModel):
    id: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    query_success_rate: float
    result_accuracy: float
    table_selection_accuracy: float
    sql_safety_accuracy: float
    dangerous_sql_block_rate: float
    approval_accuracy: float
    clarification_accuracy: float
    chart_selection_accuracy: float
    repair_success_rate: float
    fallback_rate: float
    average_latency_ms: float
    p95_latency_ms: float
    created_at: datetime
    cases: list[EvalCaseResponse] = Field(default_factory=list)


class EvalCaseDefinition(BaseModel):
    id: str
    category: str
    dataset_id: str
    question: str
    expected_status: str
    expected_tables: list[str] = Field(default_factory=list)
    expected_columns_any: list[str] = Field(default_factory=list)
    expected_chart_type: str | None = None
    should_be_blocked: bool = False
    should_require_approval: bool = False
    result_assertion: dict[str, Any] | None = None
    setup_question: str | None = None
    expected_repair: bool = False
