from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=64)
    conversation_id: str | None = None
    question: str = Field(min_length=2, max_length=2000)
    request_id: str | None = Field(default=None, max_length=64)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question cannot be blank")
        return value


class TraceEvent(BaseModel):
    id: str | None = None
    step_index: int
    node_name: str
    event_type: str
    status: str
    input_summary: str | None = None
    output_summary: str | None = None
    latency_ms: float = 0.0
    created_at: str | None = None


class ApprovalSummary(BaseModel):
    id: str
    risk_level: str
    reasons: list[str]
    sql_preview: str


class QueryResponse(BaseModel):
    request_id: str
    conversation_id: str | None
    query_log_id: str
    status: str
    question: str
    rewritten_question: str | None = None
    clarification_question: str | None = None
    selected_tables: list[str] = Field(default_factory=list)
    selected_columns: list[str] = Field(default_factory=list)
    sql: str | None = None
    safe_sql: bool = False
    safety_reason: str | None = None
    risk_level: Literal["low", "medium", "high"] = "low"
    approval: ApprovalSummary | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    chart: dict[str, Any] | None = None
    insight: str | None = None
    lineage: dict[str, Any] | None = None
    execution_time_ms: float = 0.0
    trace: list[TraceEvent] = Field(default_factory=list)
    used_fallback: bool = False
    error: dict[str, Any] | None = None
