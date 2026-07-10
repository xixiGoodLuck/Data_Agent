from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.types import interrupt
from sqlalchemy import select

from app.agent.events import EventRecorder
from app.agent.llm import BaseLLMClient, LLMClientResolver
from app.agent.routing import prompt_guard_reason
from app.agent.state import DataAnalysisState
from app.charts.planner import plan_chart
from app.core.config import Settings
from app.core.db import MetadataDatabase
from app.core.errors import AppError
from app.data.registry import resolve_dataset_path
from app.data.schema_reader import compact_schema_context, inspect_database, schema_hash
from app.models import (
    AgentRun,
    ApprovalRequest,
    Conversation,
    ConversationMessage,
    Dataset,
    QueryLog,
)
from app.sql.executor import execute_read_only
from app.sql.repair import may_repair
from app.sql.risk import assess_query_risk
from app.sql.validator import validate_sql


class AnalysisNodes:
    def __init__(
        self,
        *,
        settings: Settings,
        metadata: MetadataDatabase,
        llm: LLMClientResolver,
    ) -> None:
        self.settings = settings
        self.metadata = metadata
        self.llm = llm
        self.events = EventRecorder(metadata)

    def _llm_client(self, state: DataAnalysisState) -> BaseLLMClient:
        return self.llm.for_request(state["request_id"])

    def _start(
        self,
        state: DataAnalysisState,
        node: str,
        input_summary: Any = None,
        *,
        event_type: str = "node_started",
    ) -> tuple[float, dict[str, Any]]:
        return (
            time.perf_counter(),
            self.events.start(state, node, event_type=event_type, input_summary=input_summary),
        )

    def _complete(
        self,
        state: DataAnalysisState,
        node: str,
        started_at: float,
        started_event: dict[str, Any],
        *,
        output_summary: Any = None,
        event_type: str = "node_completed",
        status: str = "completed",
    ) -> list[dict[str, Any]]:
        completed = self.events.complete(
            state,
            node,
            started_event,
            event_type=event_type,
            status=status,
            output_summary=output_summary,
            latency_ms=(time.perf_counter() - started_at) * 1000,
        )
        return [started_event, completed]

    def intake_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "intake_node"
        started_at, started = self._start(
            state,
            node,
            {"dataset_id": state.get("dataset_id"), "run_mode": state.get("run_mode")},
            event_type="run_started",
        )
        events = self._complete(
            state,
            node,
            started_at,
            started,
            output_summary={"request_id": state.get("request_id")},
        )
        return {
            "status": "processing",
            "safe_sql": False,
            "risk_level": "low",
            "risk_reasons": [],
            "requires_approval": False,
            "repair_attempts": state.get("repair_attempts", 0),
            "used_fallback": state.get("used_fallback", False),
            "events": events,
        }

    def prompt_guard_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "prompt_guard_node"
        started_at, started = self._start(state, node, {"question_length": len(state["question"])})
        reason = prompt_guard_reason(state["question"])
        if reason:
            events = self._complete(
                state,
                node,
                started_at,
                started,
                output_summary=reason,
                event_type="sql_blocked",
                status="blocked",
            )
            return {
                "status": "blocked",
                "safety_reason": reason,
                "errors": [{"type": "prompt_blocked", "message": reason}],
                "events": events,
            }
        return {
            "events": self._complete(
                state, node, started_at, started, output_summary="Prompt policy passed"
            )
        }

    def load_dataset_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "load_dataset_node"
        started_at, started = self._start(state, node, {"dataset_id": state["dataset_id"]})
        with self.metadata.session() as session:
            dataset = session.get(Dataset, state["dataset_id"])
            if dataset is None:
                reason = "The selected dataset does not exist."
                return {
                    "status": "failed",
                    "errors": [{"type": "dataset_not_found", "message": reason}],
                    "events": self._complete(
                        state,
                        node,
                        started_at,
                        started,
                        output_summary=reason,
                        event_type="node_failed",
                        status="failed",
                    ),
                }
            try:
                path = resolve_dataset_path(dataset, self.settings)
            except AppError as exc:
                return {
                    "status": "failed",
                    "errors": [{"type": exc.error_type, "message": exc.message}],
                    "events": self._complete(
                        state,
                        node,
                        started_at,
                        started,
                        output_summary=exc.message,
                        event_type="node_failed",
                        status="failed",
                    ),
                }
            tables = json.loads(dataset.tables_json)
            name = dataset.name
        return {
            "dataset_name": name,
            "dataset_db_path": str(path),
            "available_tables": tables,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"dataset": name, "tables": tables},
            ),
        }

    def load_conversation_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "load_conversation_node"
        started_at, started = self._start(
            state, node, {"conversation_id": state.get("conversation_id")}
        )
        history: list[dict[str, Any]] = []
        conversation_id = state.get("conversation_id")
        if conversation_id:
            with self.metadata.session() as session:
                messages = list(
                    session.scalars(
                        select(ConversationMessage)
                        .where(ConversationMessage.conversation_id == conversation_id)
                        .order_by(ConversationMessage.created_at.desc())
                        .limit(self.settings.max_history_messages + 1)
                    )
                )
                messages.reverse()
                # The current user message is already stored; keep it out of prior context.
                if (
                    messages
                    and messages[-1].role == "user"
                    and messages[-1].content == state["question"]
                ):
                    messages = messages[:-1]
                history = [
                    {"role": message.role, "content": message.content[:2000]}
                    for message in messages
                ][-self.settings.max_history_messages :]
        return {
            "conversation_history": history,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"history_messages": len(history)},
            ),
        }

    def rewrite_question_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "rewrite_question_node"
        started_at, started = self._start(state, node)
        llm = self._llm_client(state)
        result = llm.rewrite_question(state["question"], state.get("conversation_history", []))
        return {
            "rewritten_question": result.rewritten_question,
            "used_fallback": state.get("used_fallback", False) or llm.last_used_fallback,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"used_history": result.used_history},
            ),
        }

    def select_tables_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "select_tables_node"
        started_at, started = self._start(state, node)
        llm = self._llm_client(state)
        with self.metadata.session() as session:
            dataset = session.get(Dataset, state["dataset_id"])
            stored_schema = json.loads(dataset.schema_json) if dataset else {}
        catalog = {
            table: {
                "columns": [
                    {"name": column["name"], "type": column.get("type", "TEXT")}
                    for column in stored_schema.get(table, {}).get("columns", [])
                ],
                "foreign_keys": stored_schema.get(table, {}).get("foreign_keys", []),
            }
            for table in state.get("available_tables", [])
        }
        result = llm.select_tables(
            state["dataset_id"],
            state.get("rewritten_question") or state["question"],
            catalog,
        )
        selected = [table for table in result.tables if table in state.get("available_tables", [])]
        if result.needs_clarification or not selected:
            clarification = (
                result.clarification_question or "Which business metric should be analyzed?"
            )
            return {
                "selected_tables": [],
                "status": "needs_clarification",
                "clarification_question": clarification,
                "used_fallback": state.get("used_fallback", False) or llm.last_used_fallback,
                "events": self._complete(
                    state,
                    node,
                    started_at,
                    started,
                    output_summary=clarification,
                    status="needs_clarification",
                ),
            }
        return {
            "selected_tables": selected,
            "used_fallback": state.get("used_fallback", False) or llm.last_used_fallback,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"selected_tables": selected, "reason": result.reason},
            ),
        }

    def read_schema_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "read_schema_node"
        started_at, started = self._start(
            state, node, {"selected_tables": state["selected_tables"]}
        )
        with self.metadata.session() as session:
            dataset = session.get(Dataset, state["dataset_id"])
            stored = json.loads(dataset.schema_json) if dataset else {}
        sensitive = {
            f"{table}.{column['name']}"
            for table, details in stored.items()
            for column in details.get("columns", [])
            if column.get("sensitive")
        }
        schema = inspect_database(
            Path(state["dataset_db_path"]),
            selected_tables=state["selected_tables"],
            sensitive_columns=sensitive,
            sample_limit=3,
        )
        digest = schema_hash(schema)
        return {
            "dataset_schema": schema,
            "schema_context": compact_schema_context(schema),
            "schema_hash": digest,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"tables": list(schema), "schema_hash": digest[:12]},
            ),
        }

    def generate_sql_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "generate_sql_node"
        started_at, started = self._start(state, node)
        llm = self._llm_client(state)
        result = llm.generate_sql(
            state["dataset_id"],
            state.get("rewritten_question") or state["question"],
            state["selected_tables"],
            state["dataset_schema"],
            state.get("schema_context") or "",
        )
        return {
            "generated_sql": result.sql,
            "sql_explanation": result.explanation,
            "selected_columns": result.selected_columns,
            "used_fallback": state.get("used_fallback", False) or llm.last_used_fallback,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"sql": result.sql},
                event_type="sql_generated",
            ),
        }

    def validate_sql_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "validate_sql_node"
        started_at, started = self._start(state, node)
        validation = validate_sql(
            state.get("generated_sql"),
            allowed_tables=state["selected_tables"],
            schema=state["dataset_schema"],
            max_rows=self.settings.max_result_rows,
        )
        if not validation.safe:
            reason = validation.reason or "The SQL did not pass validation."
            return {
                "safe_sql": False,
                "safety_reason": reason,
                "status": "blocked",
                "errors": [{"type": "sql_safety_block", "message": reason}],
                "events": self._complete(
                    state,
                    node,
                    started_at,
                    started,
                    output_summary={"reason_code": validation.reason_code, "reason": reason},
                    event_type="sql_blocked",
                    status="blocked",
                ),
            }
        lineage = {
            "tables": validation.referenced_tables,
            "columns": validation.referenced_columns,
            "schema_hash": state.get("schema_hash"),
        }
        return {
            "safe_sql": True,
            "safety_reason": None,
            "normalized_sql": validation.normalized_sql,
            "selected_columns": validation.referenced_columns,
            "lineage": lineage,
            "status": "processing",
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"tables": validation.referenced_tables, "safe": True},
            ),
        }

    def assess_risk_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "assess_risk_node"
        started_at, started = self._start(state, node)
        assessment = assess_query_risk(
            state["normalized_sql"],
            schema=state["dataset_schema"],
            referenced_columns=state.get("selected_columns", []),
        )
        updates: dict[str, Any] = {
            "risk_level": assessment.level,
            "risk_reasons": assessment.reasons,
            "requires_approval": assessment.requires_approval,
        }
        event_type = "node_completed"
        if assessment.requires_approval:
            with self.metadata.session() as session:
                approval = session.scalar(
                    select(ApprovalRequest).where(
                        ApprovalRequest.query_log_id == state["query_log_id"]
                    )
                )
                if approval is None:
                    approval = ApprovalRequest(
                        query_log_id=state["query_log_id"],
                        thread_id=state["thread_id"],
                        risk_level=assessment.level,
                        reasons_json=json.dumps(assessment.reasons),
                        sql_preview=state["normalized_sql"],
                        selected_tables_json=json.dumps(state["selected_tables"]),
                        selected_columns_json=json.dumps(state.get("selected_columns", [])),
                        status="pending",
                    )
                    session.add(approval)
                    session.flush()
                query_log = session.get(QueryLog, state["query_log_id"])
                if query_log:
                    query_log.status = "pending_approval"
                    query_log.approval_id = approval.id
                    query_log.risk_level = assessment.level
                    query_log.rewritten_question = state.get("rewritten_question")
                    query_log.selected_tables_json = json.dumps(state.get("selected_tables", []))
                    query_log.selected_columns_json = json.dumps(state.get("selected_columns", []))
                    query_log.schema_hash = state.get("schema_hash")
                    query_log.generated_sql = state.get("generated_sql")
                    query_log.normalized_sql = state.get("normalized_sql")
                    query_log.safe_sql = state.get("safe_sql", False)
                updates["approval_id"] = approval.id
                updates["status"] = "pending_approval"
            event_type = "approval_required"
        updates["events"] = self._complete(
            state,
            node,
            started_at,
            started,
            output_summary={"risk_level": assessment.level, "reasons": assessment.reasons},
            event_type=event_type,
            status="pending" if assessment.requires_approval else "completed",
        )
        return updates

    def approval_interrupt_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "approval_interrupt_node"
        started_at, started = self._start(state, node, {"approval_id": state.get("approval_id")})
        payload = {
            "approval_id": state.get("approval_id"),
            "question": state["question"],
            "sql_preview": state.get("normalized_sql"),
            "selected_tables": state.get("selected_tables", []),
            "selected_columns": state.get("selected_columns", []),
            "risk_level": state.get("risk_level", "medium"),
            "risk_reasons": state.get("risk_reasons", []),
        }
        decision = interrupt(payload)
        approved = bool(isinstance(decision, dict) and decision.get("approved"))
        status = "processing" if approved else "rejected"
        with self.metadata.session() as session:
            approval = session.get(ApprovalRequest, state.get("approval_id"))
            if approval and approval.status == "pending":
                approval.status = "approved" if approved else "rejected"
                approval.decision_note = (
                    decision.get("note") if isinstance(decision, dict) else None
                )
                approval.decided_at = datetime.now(UTC)
            query_log = session.get(QueryLog, state["query_log_id"])
            if query_log:
                query_log.status = status
        return {
            "approval_decision": decision if isinstance(decision, dict) else {"approved": False},
            "status": status,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"approved": approved},
                event_type="approval_resumed",
                status="approved" if approved else "rejected",
            ),
        }

    def execute_sql_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "execute_sql_node"
        started_at, started = self._start(state, node)
        result = execute_read_only(
            db_path=Path(state["dataset_db_path"]),
            sql=state["normalized_sql"],
            datasets_dir=self.settings.datasets_dir,
            metadata_paths={self.settings.app_db_path, self.settings.checkpoint_db_path},
            timeout_seconds=self.settings.query_timeout_seconds,
            max_rows=self.settings.max_result_rows,
        )
        if result.success:
            return {
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "execution_outcome": "success",
                "execution_error": None,
                "status": "processing",
                "events": self._complete(
                    state,
                    node,
                    started_at,
                    started,
                    output_summary={"row_count": result.row_count},
                    event_type="query_executed",
                ),
            }
        repair = may_repair(result.error_type, result.repairable, state.get("repair_attempts", 0))
        error = {
            "type": result.error_type or "query_execution_error",
            "message": result.error_message or "The query could not be executed.",
            "repairable": repair,
        }
        return {
            "execution_outcome": "repair" if repair else "failed",
            "execution_error": error,
            "status": "repair_needed" if repair else "failed",
            "errors": [error],
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"error_type": error["type"], "repairable": repair},
                event_type="node_failed",
                status="repairing" if repair else "failed",
            ),
        }

    def repair_sql_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "repair_sql_node"
        started_at, started = self._start(state, node)
        error = state.get("execution_error") or {}
        llm = self._llm_client(state)
        result = llm.repair_sql(
            state["dataset_id"],
            state.get("rewritten_question") or state["question"],
            state["normalized_sql"],
            error.get("type", "query_execution_error"),
            state.get("schema_context") or "",
        )
        return {
            "generated_sql": result.sql,
            "normalized_sql": None,
            "safe_sql": False,
            "repair_attempts": state.get("repair_attempts", 0) + 1,
            "execution_outcome": None,
            "execution_error": None,
            "status": "processing",
            "used_fallback": state.get("used_fallback", False) or llm.last_used_fallback,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"repaired_sql": result.sql},
                event_type="sql_generated",
            ),
        }

    def plan_chart_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "plan_chart_node"
        started_at, started = self._start(state, node)
        chart = plan_chart(state["question"], state.get("columns", []), state.get("rows", []))
        return {
            "chart": chart.model_dump(),
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"chart_type": chart.type},
                event_type="chart_planned",
            ),
        }

    def write_insight_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "write_insight_node"
        started_at, started = self._start(state, node)
        llm = self._llm_client(state)
        result = llm.write_insight(
            state["question"],
            state["normalized_sql"],
            state.get("columns", []),
            state.get("rows", []),
        )
        return {
            "insight": result.insight,
            "used_fallback": state.get("used_fallback", False) or llm.last_used_fallback,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"insight_length": len(result.insight)},
                event_type="insight_generated",
            ),
        }

    def persist_result_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "persist_result_node"
        started_at, started = self._start(state, node)
        status = state.get("status", "failed")
        if status == "processing":
            status = "success"
        elapsed = max(0.0, time.time() * 1000 - state.get("started_at_epoch_ms", 0.0))
        last_error = (
            state.get("errors", [])[-1] if state.get("errors") and status != "success" else None
        )
        with self.metadata.session() as session:
            query_log = session.get(QueryLog, state["query_log_id"])
            if query_log:
                query_log.rewritten_question = state.get("rewritten_question")
                query_log.selected_tables_json = json.dumps(state.get("selected_tables", []))
                query_log.selected_columns_json = json.dumps(state.get("selected_columns", []))
                query_log.schema_hash = state.get("schema_hash")
                query_log.generated_sql = state.get("generated_sql")
                query_log.normalized_sql = state.get("normalized_sql")
                query_log.status = status
                query_log.safe_sql = state.get("safe_sql", False)
                query_log.safety_reason = state.get("safety_reason")
                query_log.risk_level = state.get("risk_level", "low")
                query_log.approval_id = state.get("approval_id")
                query_log.row_count = state.get("row_count", 0)
                query_log.chart_type = (state.get("chart") or {}).get("type")
                query_log.execution_time_ms = elapsed
                query_log.used_fallback = state.get("used_fallback", False)
                query_log.error_type = last_error.get("type") if last_error else None
                query_log.error_message = last_error.get("message") if last_error else None
                query_log.completed_at = datetime.now(UTC)
            run = session.get(AgentRun, state["run_id"])
            if run:
                run.status = status
                run.total_latency_ms = elapsed
        return {
            "status": status,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"status": status},
            ),
        }

    def finalize_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "finalize_node"
        started_at, started = self._start(state, node)
        completed = self._complete(
            state,
            node,
            started_at,
            started,
            output_summary={"status": state["status"]},
            event_type="run_completed",
            status=state["status"],
        )
        trace = state.get("events", []) + completed
        last_error = (
            state.get("errors", [])[-1]
            if state.get("errors") and state.get("status") != "success"
            else None
        )
        response = {
            "request_id": state["request_id"],
            "conversation_id": state.get("conversation_id"),
            "query_log_id": state["query_log_id"],
            "status": state["status"],
            "question": state["question"],
            "rewritten_question": state.get("rewritten_question"),
            "clarification_question": state.get("clarification_question"),
            "selected_tables": state.get("selected_tables", []),
            "selected_columns": state.get("selected_columns", []),
            "sql": state.get("normalized_sql") or state.get("generated_sql"),
            "safe_sql": state.get("safe_sql", False),
            "safety_reason": state.get("safety_reason"),
            "risk_level": state.get("risk_level", "low"),
            "approval": None,
            "columns": state.get("columns", []),
            "rows": state.get("rows", []),
            "row_count": state.get("row_count", 0),
            "chart": state.get("chart"),
            "insight": state.get("insight"),
            "lineage": state.get("lineage"),
            "execution_time_ms": max(
                0.0, time.time() * 1000 - state.get("started_at_epoch_ms", 0.0)
            ),
            "trace": trace,
            "used_fallback": state.get("used_fallback", False),
            "error": last_error,
        }
        with self.metadata.session() as session:
            query_log = session.get(QueryLog, state["query_log_id"])
            if query_log:
                query_log.result_json = json.dumps(response, ensure_ascii=True, default=str)
                query_log.execution_time_ms = response["execution_time_ms"]
            run = session.get(AgentRun, state["run_id"])
            if run:
                run.completed_at = datetime.now(UTC)
                run.total_latency_ms = response["execution_time_ms"]
                run.nodes_run_json = json.dumps([event["node_name"] for event in trace])
                run.status = state["status"]
            conversation_id = state.get("conversation_id")
            if conversation_id and state.get("run_mode") == "interactive":
                existing = session.scalar(
                    select(ConversationMessage).where(
                        ConversationMessage.query_log_id == state["query_log_id"],
                        ConversationMessage.role == "assistant",
                    )
                )
                if existing is None:
                    content = state.get("insight")
                    if not content:
                        content = (
                            state.get("clarification_question")
                            or (last_error or {}).get("message")
                            or f"Query finished with status: {state['status']}."
                        )
                    session.add(
                        ConversationMessage(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=content,
                            query_log_id=state["query_log_id"],
                        )
                    )
                conversation = session.get(Conversation, conversation_id)
                if conversation:
                    conversation.updated_at = datetime.now(UTC)
        return {"final_response": response, "events": completed}
