from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


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
