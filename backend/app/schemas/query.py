from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_ANALYSIS_STEPS = 5
AnalysisType = Literal["lookup", "comparison", "ranking", "trend", "diagnostic", "exploratory"]
AnalysisMode = Literal["simple_query", "investigative_analysis"]
AnalysisStepStatus = Literal["pending", "running", "completed", "skipped"]
ResultShape = Literal[
    "scalar",
    "ranking",
    "categorical_breakdown",
    "time_series",
    "period_comparison",
]


class ResultShapeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shape: ResultShape
    time_column: str | None = None
    dimension_columns: list[str] = Field(default_factory=list, max_length=20)
    metric_columns: list[str] = Field(default_factory=list, max_length=20)
    series_columns: list[str] = Field(default_factory=list, max_length=20)


class EvidenceFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(min_length=1, max_length=160)
    metric: str = Field(min_length=1, max_length=120)
    dimension: str | None = Field(default=None, max_length=120)
    dimension_value: str | None = Field(default=None, max_length=240)
    statistic: str = Field(min_length=1, max_length=120)
    value: str | int | float | bool
    unit: str | None = Field(default=None, max_length=40)


class AnalysisIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=500)
    analysis_type: AnalysisType
    metrics: list[str] = Field(default_factory=list, max_length=20)
    dimensions: list[str] = Field(default_factory=list, max_length=20)
    filters: list[str] = Field(default_factory=list, max_length=20)
    time_range: str | None = Field(default=None, max_length=200)
    comparison: str | None = Field(default=None, max_length=200)
    desired_grain: str | None = Field(default=None, max_length=100)
    needs_multi_step: bool
    reason: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def align_route_with_analysis_type(self) -> AnalysisIntent:
        self.needs_multi_step = self.analysis_type in {"diagnostic", "exploratory"}
        return self


class AnalysisStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=32)
    question: str = Field(min_length=2, max_length=500)
    purpose: str = Field(min_length=2, max_length=500)
    status: AnalysisStepStatus = "pending"

    @field_validator("question", "purpose")
    @classmethod
    def reject_sql_statements(cls, value: str) -> str:
        if re.search(
            r"\b(?:select\s+.+\s+from|insert\s+into|update\s+.+\s+set|delete\s+from|drop\s+table)\b",
            value,
            re.IGNORECASE | re.DOTALL,
        ):
            raise ValueError("Analysis steps must describe analytical questions, not SQL")
        return value.strip()


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=500)
    steps: list[AnalysisStep] = Field(min_length=1, max_length=MAX_ANALYSIS_STEPS)
    max_steps: int = Field(default=MAX_ANALYSIS_STEPS, ge=1, le=MAX_ANALYSIS_STEPS)
    status: Literal["pending", "running", "completed"] = "pending"

    @model_validator(mode="after")
    def enforce_step_limit(self) -> AnalysisPlan:
        if len(self.steps) > self.max_steps:
            raise ValueError("Analysis plan exceeds max_steps")
        return self


class AnalysisContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=500)
    active_metrics: list[str] = Field(default_factory=list, max_length=20)
    active_dimensions: list[str] = Field(default_factory=list, max_length=20)
    required_filters: list[str] = Field(default_factory=list, max_length=20)
    time_range: str | None = Field(default=None, max_length=200)
    comparison_grain: str | None = Field(default=None, max_length=200)
    grouping_grain: str | None = Field(default=None, max_length=120)
    remaining_evidence_gap: list[str] = Field(default_factory=list, max_length=20)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    step_id: str = Field(min_length=1, max_length=32)
    question: str = Field(min_length=2, max_length=500)
    sql: str = Field(min_length=1, max_length=10_000)
    result_shape: ResultShape = "scalar"
    result_shape_metadata: ResultShapeMetadata | None = None
    result_summary: str = Field(min_length=1, max_length=2_000)
    key_values: dict[str, Any] = Field(default_factory=dict)
    series_changes: dict[str, dict[str, float]] = Field(default_factory=dict)
    facts: list[EvidenceFact] = Field(default_factory=list, max_length=200)
    row_count: int = Field(ge=0)
    returned_row_count: int = Field(default=0, ge=0)
    is_truncated: bool = False
    lineage: dict[str, Any] | None = None
    limitations: list[str] = Field(default_factory=list, max_length=20)
    created_at: datetime


class CriticResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sufficient: bool
    answered_objective: bool
    missing_evidence: list[str] = Field(default_factory=list, max_length=20)
    conflicts: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    recommended_next_step: str | None = Field(default=None, max_length=500)


class NextAnalysisDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["continue", "finish", "clarify"]
    next_step: AnalysisStep | None = None
    reason: str = Field(min_length=1, max_length=240)
    plan_patch: dict[str, Any] | None = None
    context_patch: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_next_step(self) -> NextAnalysisDecision:
        if self.action == "continue" and self.next_step is None:
            raise ValueError("A continue decision requires next_step")
        if self.action != "continue":
            self.next_step = None
        return self


class AnalysisEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critic: CriticResult
    decision: NextAnalysisDecision


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=1_000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    fact_ids: list[str] = Field(default_factory=list, max_length=50)
    facts: dict[str, float] = Field(default_factory=dict)


class FinalAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executive_summary: str = Field(min_length=1, max_length=2_000)
    key_findings: list[Finding] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    recommended_actions: list[str] = Field(default_factory=list, max_length=20)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    evidence_insufficient: bool = False


class SupportingChart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_ids: list[str] = Field(min_length=1, max_length=3)
    config: dict[str, Any]
    columns: list[str] = Field(default_factory=list, max_length=20)
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=20)


def normalize_local_base_url(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    parsed = urlparse(cleaned)
    local_hosts = {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in local_hosts:
        raise ValueError("Base URL must use http(s) and point to the local machine")
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("Base URL cannot contain credentials, parameters, a query, or a fragment")
    if parsed.path not in {"", "/", "/v1", "/v1/"}:
        raise ValueError("Base URL path must be empty or /v1")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return f"{origin}/v1"


class LocalModelConfig(BaseModel):
    enabled: bool = False
    base_url: str = Field(default="", max_length=512)
    model: str = Field(default="", max_length=256)

    @model_validator(mode="after")
    def validate_enabled_config(self) -> LocalModelConfig:
        self.base_url = self.base_url.strip()
        self.model = self.model.strip()
        if self.enabled:
            if not self.base_url or not self.model:
                raise ValueError(
                    "Base URL and Model ID are required when the local model is enabled"
                )
            self.base_url = normalize_local_base_url(self.base_url)
        return self


class QueryRequest(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=64)
    conversation_id: str | None = None
    question: str = Field(min_length=2, max_length=2000)
    request_id: str | None = Field(default=None, max_length=64)
    local_model: LocalModelConfig | None = None

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
    response_language: Literal["zh-CN", "en"] = "en"
    rewritten_question: str | None = None
    analysis_mode: AnalysisMode = "simple_query"
    analysis_intent: AnalysisIntent | None = None
    analysis_plan: AnalysisPlan | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    critic_result: CriticResult | None = None
    analysis_step_count: int = 0
    evidence_insufficient: bool = False
    final_analysis: FinalAnalysis | None = None
    supporting_charts: list[SupportingChart] = Field(default_factory=list)
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
    returned_row_count: int = 0
    is_truncated: bool = False
    chart: dict[str, Any] | None = None
    insight: str | None = None
    lineage: dict[str, Any] | None = None
    execution_time_ms: float = 0.0
    trace: list[TraceEvent] = Field(default_factory=list)
    used_fallback: bool = False
    error: dict[str, Any] | None = None
