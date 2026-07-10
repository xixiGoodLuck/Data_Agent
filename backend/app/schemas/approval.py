from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApprovalDecision(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ApprovalResponse(BaseModel):
    id: str
    query_log_id: str
    thread_id: str
    question: str | None = None
    risk_level: str
    reasons: list[str]
    sql_preview: str
    selected_tables: list[str]
    selected_columns: list[str]
    status: str
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None
