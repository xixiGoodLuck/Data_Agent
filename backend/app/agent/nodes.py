from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.types import interrupt
from sqlalchemy import select

from app.agent.analysis import build_evidence
from app.agent.events import EventRecorder
from app.agent.grounding import select_supporting_charts, validate_final_analysis
from app.agent.language import detect_response_language, is_chinese
from app.agent.llm import BaseLLMClient, LLMClientResolver
from app.agent.routing import prompt_guard_reason
from app.agent.state import DataAnalysisState
from app.charts.planner import plan_chart
from app.core.config import Settings
from app.core.db import MetadataDatabase
from app.core.errors import AppError
from app.data.registry import resolve_dataset_path
from app.data.schema_reader import (
    apply_column_aliases,
    compact_schema_context,
    inspect_database,
    schema_hash,
)
from app.models import (
    AgentRun,
    ApprovalRequest,
    Conversation,
    ConversationMessage,
    Dataset,
    QueryLog,
)
from app.schemas.query import (
    AnalysisEvaluation,
    AnalysisIntent,
    AnalysisPlan,
    CriticResult,
    Evidence,
    FinalAnalysis,
    NextAnalysisDecision,
)
from app.sql.executor import execute_read_only
from app.sql.repair import may_repair
from app.sql.risk import assess_query_risk
from app.sql.validator import validate_sql


class AnalysisNodes:
    MAX_TOOL_FAILURES = 2
    MAX_DECISION_RETRIES = 2

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

    @staticmethod
    def _analysis_question(state: DataAnalysisState) -> str:
        return (
            state.get("active_analysis_question")
            or state.get("rewritten_question")
            or state["question"]
        )

    @staticmethod
    def _response_language(state: DataAnalysisState) -> str:
        return state.get("response_language") or detect_response_language(state["question"])

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
            "response_language": detect_response_language(state["question"]),
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
        result = llm.rewrite_question(
            state["question"],
            state.get("conversation_history", []),
            self._response_language(state),
        )
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

    def understand_analysis_intent_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "understand_analysis_intent_node"
        started_at, started = self._start(state, node)
        llm = self._llm_client(state)
        question = state.get("rewritten_question") or state["question"]
        intent = llm.understand_analysis_intent(question, self._response_language(state))
        analysis_mode = "investigative_analysis" if intent.needs_multi_step else "simple_query"
        return {
            "active_analysis_question": question,
            "analysis_mode": analysis_mode,
            "analysis_intent": intent.model_dump(),
            "used_fallback": state.get("used_fallback", False) or llm.last_used_fallback,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={
                    "analysis_type": intent.analysis_type,
                    "needs_multi_step": intent.needs_multi_step,
                    "objective": intent.objective,
                },
                event_type="analysis_intent_created",
            ),
        }

    def create_analysis_plan_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "create_analysis_plan_node"
        started_at, started = self._start(state, node)
        llm = self._llm_client(state)
        intent = AnalysisIntent.model_validate(state["analysis_intent"])
        question = state.get("rewritten_question") or state["question"]
        plan = llm.create_analysis_plan(
            question, intent, self._response_language(state)
        ).model_copy(deep=True)
        plan.status = "running"
        return {
            "analysis_plan": plan.model_dump(),
            "used_fallback": state.get("used_fallback", False) or llm.last_used_fallback,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={
                    "objective": plan.objective,
                    "max_steps": plan.max_steps,
                    "steps": [step.question for step in plan.steps],
                },
                event_type="analysis_plan_created",
            ),
        }

    def prepare_analysis_step_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "prepare_analysis_step_node"
        plan = AnalysisPlan.model_validate(state["analysis_plan"]).model_copy(deep=True)
        decision = state.get("next_analysis_decision") or {}
        next_step = decision.get("next_step") or {}
        requested_step_id = next_step.get("id") if decision.get("action") == "continue" else None
        step = next(
            (
                item
                for item in plan.steps
                if item.status == "pending" and item.id == requested_step_id
            ),
            None,
        )
        if step is None:
            step = next((item for item in plan.steps if item.status == "pending"), None)
        started_at, started = self._start(
            state,
            node,
            {"step_id": step.id if step else None},
        )
        if step is None:
            return {
                "evidence_insufficient": not bool(
                    (state.get("critic_result") or {}).get("sufficient")
                ),
                "next_analysis_decision": NextAnalysisDecision(
                    action="finish",
                    reason="No pending bounded analysis step remains.",
                ).model_dump(),
                "events": self._complete(
                    state,
                    node,
                    started_at,
                    started,
                    output_summary={"action": "finish", "reason": "no_pending_step"},
                    event_type="analysis_finished",
                ),
            }
        step.status = "running"
        return {
            "analysis_plan": plan.model_dump(),
            "current_analysis_step_id": step.id,
            "active_analysis_question": step.question,
            "selected_tables": [],
            "selected_columns": [],
            "dataset_schema": {},
            "schema_context": None,
            "schema_hash": None,
            "generated_sql": None,
            "sql_explanation": None,
            "normalized_sql": None,
            "safe_sql": False,
            "safety_reason": None,
            "risk_level": "low",
            "risk_reasons": [],
            "requires_approval": False,
            "approval_id": None,
            "approval_decision": None,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "lineage": None,
            "repair_attempts": 0,
            "execution_outcome": None,
            "execution_error": None,
            "status": "processing",
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"step_id": step.id, "question": step.question},
                event_type="analysis_step_started",
            ),
        }

    def select_tables_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "select_tables_node"
        started_at, started = self._start(state, node)
        llm = self._llm_client(state)
        with self.metadata.session() as session:
            dataset = session.get(Dataset, state["dataset_id"])
            stored_schema = json.loads(dataset.schema_json) if dataset else {}
            column_mapping = json.loads(dataset.column_mapping_json) if dataset else []
        source_names = {
            item["sanitized"]: str(item["original"])[:256]
            for item in column_mapping
            if isinstance(item, dict) and item.get("sanitized") and item.get("original")
        }
        catalog = {
            table: {
                "columns": [
                    {
                        "name": column["name"],
                        "type": column.get("type", "TEXT"),
                        **(
                            {"source_name": source_names[column["name"]]}
                            if column["name"] in source_names
                            else {}
                        ),
                    }
                    for column in stored_schema.get(table, {}).get("columns", [])
                ],
                "foreign_keys": stored_schema.get(table, {}).get("foreign_keys", []),
            }
            for table in state.get("available_tables", [])
        }
        result = llm.select_tables(
            state["dataset_id"],
            self._analysis_question(state),
            catalog,
            self._response_language(state),
        )
        selected = [table for table in result.tables if table in state.get("available_tables", [])]
        if result.needs_clarification or not selected:
            clarification = result.clarification_question or (
                "你希望分析哪个业务指标?"
                if is_chinese(self._response_language(state))
                else "Which business metric should be analyzed?"
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
                    event_type=(
                        "query_tool_called"
                        if state.get("analysis_mode") == "investigative_analysis"
                        else "node_completed"
                    ),
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
                event_type=(
                    "query_tool_called"
                    if state.get("analysis_mode") == "investigative_analysis"
                    else "node_completed"
                ),
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
            column_mapping = json.loads(dataset.column_mapping_json) if dataset else []
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
        apply_column_aliases(schema, column_mapping)
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
            self._analysis_question(state),
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
        tool_failures = state.get("tool_failures", 0) + 1
        repair = tool_failures <= self.MAX_TOOL_FAILURES and may_repair(
            result.error_type, result.repairable, state.get("repair_attempts", 0)
        )
        error = {
            "type": result.error_type or "query_execution_error",
            "message": result.error_message or "The query could not be executed.",
            "repairable": repair,
        }
        return {
            "execution_outcome": "repair" if repair else "failed",
            "execution_error": error,
            "tool_failures": tool_failures,
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
            self._analysis_question(state),
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

    def create_evidence_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "create_evidence_node"
        step_id = state["current_analysis_step_id"]
        started_at, started = self._start(state, node, {"step_id": step_id})
        evidence_by_step = dict(state.get("evidence_by_step", {}))
        if step_id in evidence_by_step:
            evidence = Evidence.model_validate(evidence_by_step[step_id])
        else:
            evidence = build_evidence(state)
            evidence_by_step[step_id] = evidence.model_dump(mode="json")

        plan = AnalysisPlan.model_validate(state["analysis_plan"]).model_copy(deep=True)
        for step in plan.steps:
            if step.id == step_id:
                step.status = "completed"
                break
        return {
            "analysis_plan": plan.model_dump(),
            "evidence_by_step": evidence_by_step,
            "analysis_step_count": len(evidence_by_step),
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={
                    "evidence_id": evidence.id,
                    "step_id": evidence.step_id,
                    "result_summary": evidence.result_summary,
                    "key_values": evidence.key_values,
                    "row_count": evidence.row_count,
                    "limitations": evidence.limitations,
                },
                event_type="evidence_created",
            ),
        }

    def evaluate_analysis_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "evaluate_analysis_node"
        started_at, started = self._start(
            state,
            node,
            {"analysis_step_count": state.get("analysis_step_count", 0)},
        )
        intent = AnalysisIntent.model_validate(state["analysis_intent"])
        plan = AnalysisPlan.model_validate(state["analysis_plan"]).model_copy(deep=True)
        evidence_by_step = state.get("evidence_by_step", {})
        evidence = [
            Evidence.model_validate(evidence_by_step[step.id])
            for step in plan.steps
            if step.id in evidence_by_step
        ]
        for step_id, payload in evidence_by_step.items():
            if not any(item.step_id == step_id for item in evidence):
                evidence.append(Evidence.model_validate(payload))

        forced_limit = len(evidence) >= plan.max_steps
        if forced_limit:
            evaluation = AnalysisEvaluation(
                critic=CriticResult(
                    sufficient=False,
                    answered_objective=False,
                    missing_evidence=[
                        "已达到分析步骤的硬性上限。"
                        if is_chinese(self._response_language(state))
                        else "The hard analysis-step limit was reached."
                    ],
                    limitations=[
                        limitation for item in evidence for limitation in item.limitations
                    ][:20],
                    recommended_next_step=None,
                ),
                decision=NextAnalysisDecision(
                    action="finish",
                    reason=(
                        "已达到配置的分析步骤上限。"
                        if is_chinese(self._response_language(state))
                        else "The configured analysis-step limit was reached."
                    ),
                ),
            )
        else:
            llm = self._llm_client(state)
            retries = state.get("decision_retries", 0)
            while True:
                try:
                    evaluation = llm.evaluate_analysis(
                        intent, plan, evidence, self._response_language(state)
                    )
                    break
                except AppError as exc:
                    if retries >= self.MAX_DECISION_RETRIES or exc.error_type not in {
                        "llm_invalid_output",
                        "llm_request_error",
                        "local_model_error",
                    }:
                        raise
                    retries += 1

        decision = evaluation.decision.model_copy(deep=True)
        if evaluation.critic.sufficient:
            decision = NextAnalysisDecision(
                action="finish",
                reason=decision.reason,
                plan_patch=decision.plan_patch,
            )

        if decision.action == "continue" and decision.next_step:
            target = next(
                (step for step in plan.steps if step.id == decision.next_step.id),
                None,
            )
            if target and target.status == "pending":
                target.question = decision.next_step.question
                target.purpose = decision.next_step.purpose
            elif target is None and len(plan.steps) < plan.max_steps:
                plan.steps.append(decision.next_step)
            elif target is None:
                replacement_index = next(
                    (index for index, step in enumerate(plan.steps) if step.status == "pending"),
                    None,
                )
                if replacement_index is not None:
                    plan.steps[replacement_index] = decision.next_step
                else:
                    decision = NextAnalysisDecision(
                        action="finish",
                        reason=(
                            "娌℃湁鍙帴鏀朵笅涓€鍐崇瓥鐨勬湁闄愬緟鎵ц姝ラ銆?"
                            if is_chinese(self._response_language(state))
                            else "No bounded pending step can accept the next decision."
                        ),
                        plan_patch=decision.plan_patch,
                    )
                    forced_limit = True
            else:
                decision = NextAnalysisDecision(
                    action="finish",
                    reason=(
                        "没有可接收下一决策的有限待执行步骤。"
                        if is_chinese(self._response_language(state))
                        else "No bounded pending step can accept the next decision."
                    ),
                    plan_patch=decision.plan_patch,
                )
                forced_limit = True

        if decision.action == "clarify":
            status = "needs_clarification"
            clarification = (
                evaluation.critic.missing_evidence[0]
                if evaluation.critic.missing_evidence
                else decision.reason
            )
        else:
            status = "processing"
            clarification = None

        critic_event = self.events.complete(
            state,
            node,
            started,
            event_type="critic_completed",
            status="completed",
            output_summary=evaluation.critic.model_dump(),
            latency_ms=(time.perf_counter() - started_at) * 1000,
        )
        decision_event = self.events.record(
            state,
            node_name=node,
            event_type="analysis_decision",
            status=decision.action,
            step_index=critic_event["step_index"] + 1,
            output_summary={
                "action": decision.action,
                "reason": decision.reason,
                "next_step": decision.next_step.model_dump() if decision.next_step else None,
                "plan_patch": decision.plan_patch,
            },
        )
        return {
            "analysis_plan": plan.model_dump(),
            "critic_result": evaluation.critic.model_dump(),
            "next_analysis_decision": decision.model_dump(),
            "decision_retries": retries if not forced_limit else state.get("decision_retries", 0),
            "evidence_insufficient": forced_limit
            or (decision.action == "finish" and not evaluation.critic.sufficient),
            "clarification_question": clarification,
            "status": status,
            "used_fallback": state.get("used_fallback", False)
            or (not forced_limit and self._llm_client(state).last_used_fallback),
            "events": [started, critic_event, decision_event],
        }

    def finish_analysis_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "finish_analysis_node"
        started_at, started = self._start(state, node)
        plan = AnalysisPlan.model_validate(state["analysis_plan"]).model_copy(deep=True)
        for step in plan.steps:
            if step.status == "pending":
                step.status = "skipped"
        plan.status = "completed"
        evidence_by_step = state.get("evidence_by_step", {})
        evidence = [
            Evidence.model_validate(evidence_by_step[step.id])
            for step in plan.steps
            if step.id in evidence_by_step
        ]
        return {
            "analysis_plan": plan.model_dump(),
            "status": "processing",
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={
                    "analysis_step_count": len(evidence),
                    "evidence_insufficient": state.get("evidence_insufficient", False),
                },
                event_type="analysis_finished",
            ),
        }

    def synthesize_final_analysis_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "synthesize_final_analysis_node"
        started_at, started = self._start(state, node, event_type="final_synthesis_started")
        plan = AnalysisPlan.model_validate(state["analysis_plan"])
        intent = AnalysisIntent.model_validate(state["analysis_intent"])
        evidence_by_step = state.get("evidence_by_step", {})
        evidence = [
            Evidence.model_validate(evidence_by_step[step.id])
            for step in plan.steps
            if step.id in evidence_by_step
        ]
        critic = (
            CriticResult.model_validate(state["critic_result"])
            if state.get("critic_result")
            else None
        )
        llm = self._llm_client(state)
        analysis = llm.synthesize_analysis(
            state["question"],
            intent,
            plan,
            evidence,
            critic,
            state.get("evidence_insufficient", False),
            self._response_language(state),
        )
        return {
            "final_analysis": analysis.model_dump(),
            "used_fallback": state.get("used_fallback", False) or llm.last_used_fallback,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={
                    "finding_count": len(analysis.key_findings),
                    "evidence_ids": analysis.evidence_ids,
                },
                event_type="final_synthesis_completed",
            ),
        }

    def validate_final_analysis_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "validate_final_analysis_node"
        started_at, started = self._start(state, node)
        evidence = [
            Evidence.model_validate(item) for item in state.get("evidence_by_step", {}).values()
        ]
        analysis = validate_final_analysis(
            FinalAnalysis.model_validate(state["final_analysis"]),
            evidence,
            evidence_insufficient=state.get("evidence_insufficient", False),
        )
        return {
            "final_analysis": analysis.model_dump(),
            "insight": analysis.executive_summary,
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"grounded": True, "evidence_ids": analysis.evidence_ids},
                event_type="final_grounding_validated",
            ),
        }

    def select_supporting_charts_node(self, state: DataAnalysisState) -> dict[str, Any]:
        node = "select_supporting_charts_node"
        started_at, started = self._start(state, node)
        evidence = [
            Evidence.model_validate(item) for item in state.get("evidence_by_step", {}).values()
        ]
        analysis = FinalAnalysis.model_validate(state["final_analysis"])
        charts = select_supporting_charts(evidence, analysis.evidence_ids)
        return {
            "supporting_charts": [chart.model_dump() for chart in charts],
            "events": self._complete(
                state,
                node,
                started_at,
                started,
                output_summary={"chart_count": len(charts)},
                event_type="supporting_charts_selected",
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
            self._analysis_question(state),
            state["normalized_sql"],
            state.get("columns", []),
            state.get("rows", []),
            self._response_language(state),
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
        response_plan = state.get("analysis_plan")
        evidence_by_step = state.get("evidence_by_step", {})
        response_evidence: list[dict[str, Any]] = []
        if response_plan:
            plan = AnalysisPlan.model_validate(response_plan)
            response_evidence = [
                Evidence.model_validate(evidence_by_step[step.id]).model_dump(mode="json")
                for step in plan.steps
                if step.id in evidence_by_step
            ]
        response = {
            "request_id": state["request_id"],
            "conversation_id": state.get("conversation_id"),
            "query_log_id": state["query_log_id"],
            "status": state["status"],
            "question": state["question"],
            "response_language": self._response_language(state),
            "rewritten_question": state.get("rewritten_question"),
            "analysis_mode": state.get("analysis_mode", "simple_query"),
            "analysis_intent": state.get("analysis_intent"),
            "analysis_plan": response_plan,
            "evidence": response_evidence,
            "critic_result": state.get("critic_result"),
            "analysis_step_count": state.get("analysis_step_count", 0),
            "evidence_insufficient": state.get("evidence_insufficient", False),
            "final_analysis": state.get("final_analysis"),
            "supporting_charts": state.get("supporting_charts", []),
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
                    content = (state.get("final_analysis") or {}).get(
                        "executive_summary"
                    ) or state.get("insight")
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
