from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, new_uuid, utcnow


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    query_success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    result_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    table_selection_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    sql_safety_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    dangerous_sql_block_rate: Mapped[float] = mapped_column(Float, default=0.0)
    approval_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    clarification_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    chart_selection_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    repair_success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    fallback_rate: Mapped[float] = mapped_column(Float, default=0.0)
    average_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    p95_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    cases: Mapped[list[EvalCaseResult]] = relationship(
        back_populates="eval_run", cascade="all, delete-orphan"
    )


class EvalCaseResult(Base):
    __tablename__ = "eval_case_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    eval_run_id: Mapped[str] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="general")
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    actual_tables_json: Mapped[str] = mapped_column(Text, default="[]")
    actual_chart_type: Mapped[str | None] = mapped_column(String(24))
    expected_json: Mapped[str] = mapped_column(Text, default="{}")
    actual_json: Mapped[str] = mapped_column(Text, default="{}")
    failure_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)

    eval_run: Mapped[EvalRun] = relationship(back_populates="cases")
