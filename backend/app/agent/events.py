from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from langgraph.config import get_stream_writer
from sqlalchemy import select

from app.agent.state import DataAnalysisState
from app.core.db import MetadataDatabase
from app.models import AgentEvent


def _sanitize_summary(value: Any, max_length: int = 500) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=True, default=str, separators=(",", ":"))
    text = " ".join(text.split())
    return text[:max_length]


class EventRecorder:
    def __init__(self, metadata: MetadataDatabase) -> None:
        self.metadata = metadata

    def record(
        self,
        state: DataAnalysisState,
        *,
        node_name: str,
        event_type: str,
        status: str,
        step_index: int,
        input_summary: Any = None,
        output_summary: Any = None,
        latency_ms: float = 0.0,
    ) -> dict[str, Any]:
        run_id = state.get("run_id") or "unpersisted"
        event_id = str(
            uuid5(NAMESPACE_URL, f"insightops:{run_id}:{step_index}:{node_name}:{event_type}")
        )
        event = {
            "id": event_id,
            "step_index": step_index,
            "node_name": node_name,
            "event_type": event_type,
            "status": status,
            "input_summary": _sanitize_summary(input_summary),
            "output_summary": _sanitize_summary(output_summary),
            "latency_ms": round(latency_ms, 3),
            "created_at": datetime.now(UTC).isoformat(),
        }
        if state.get("run_id") and state.get("query_log_id"):
            with self.metadata.session() as session:
                existing = session.scalar(select(AgentEvent).where(AgentEvent.id == event_id))
                if existing is None:
                    session.add(
                        AgentEvent(
                            id=event_id,
                            run_id=state["run_id"],
                            query_log_id=state["query_log_id"],
                            step_index=step_index,
                            node_name=node_name,
                            event_type=event_type,
                            status=status,
                            input_summary=event["input_summary"],
                            output_summary=event["output_summary"],
                            latency_ms=event["latency_ms"],
                        )
                    )
        try:
            writer = get_stream_writer()
            writer({"kind": "trace", "event": event})
        except (RuntimeError, LookupError):
            pass
        return event

    def start(
        self,
        state: DataAnalysisState,
        node_name: str,
        *,
        event_type: str = "node_started",
        input_summary: Any = None,
    ) -> dict[str, Any]:
        return self.record(
            state,
            node_name=node_name,
            event_type=event_type,
            status="running",
            step_index=len(state.get("events", [])) + 1,
            input_summary=input_summary,
        )

    def complete(
        self,
        state: DataAnalysisState,
        node_name: str,
        started_event: dict[str, Any],
        *,
        event_type: str = "node_completed",
        status: str = "completed",
        output_summary: Any = None,
        latency_ms: float = 0.0,
    ) -> dict[str, Any]:
        return self.record(
            state,
            node_name=node_name,
            event_type=event_type,
            status=status,
            step_index=started_event["step_index"] + 1,
            output_summary=output_summary,
            latency_ms=latency_ms,
        )
