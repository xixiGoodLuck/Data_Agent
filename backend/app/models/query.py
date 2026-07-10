from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, new_uuid, utcnow


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="interactive")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_question: Mapped[str | None] = mapped_column(Text)
    selected_tables_json: Mapped[str] = mapped_column(Text, default="[]")
    selected_columns_json: Mapped[str] = mapped_column(Text, default="[]")
    schema_hash: Mapped[str | None] = mapped_column(String(64))
    generated_sql: Mapped[str | None] = mapped_column(Text)
    normalized_sql: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    safe_sql: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    safety_reason: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chart_type: Mapped[str | None] = mapped_column(String(24))
    execution_time_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    used_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_type: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    runs: Mapped[list[AgentRun]] = relationship(
        back_populates="query_log", cascade="all, delete-orphan"
    )
    events: Mapped[list[AgentEvent]] = relationship(
        back_populates="query_log", cascade="all, delete-orphan"
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    query_log_id: Mapped[str] = mapped_column(
        ForeignKey("query_logs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    nodes_run_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    query_log: Mapped[QueryLog] = relationship(back_populates="runs")
    events: Mapped[list[AgentEvent]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AgentEvent(Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "step_index", "node_name", "event_type", name="uq_agent_event_step"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_log_id: Mapped[str] = mapped_column(
        ForeignKey("query_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="events")
    query_log: Mapped[QueryLog] = relationship(back_populates="events")
