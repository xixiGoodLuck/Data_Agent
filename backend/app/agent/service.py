from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from langgraph.types import Command
from sqlalchemy import select

from app.agent.language import detect_response_language
from app.agent.llm import LLMClientResolver, get_deepseek_client, get_local_model_client
from app.agent.state import DataAnalysisState
from app.core.config import Settings
from app.core.db import MetadataDatabase
from app.core.errors import AppError
from app.models import (
    AgentEvent,
    AgentRun,
    ApprovalRequest,
    Conversation,
    ConversationMessage,
    Dataset,
    QueryLog,
)
from app.schemas.query import LocalModelConfig

logger = logging.getLogger(__name__)


@dataclass
class PreparedRun:
    state: DataAnalysisState | None
    config: dict[str, Any]
    cached_response: dict[str, Any] | None = None


class QueryService:
    def __init__(
        self,
        *,
        settings: Settings,
        metadata: MetadataDatabase,
        graph: Any,
        llm_resolver: LLMClientResolver,
    ) -> None:
        self.settings = settings
        self.metadata = metadata
        self.graph = graph
        self.llm_resolver = llm_resolver

    def prepare_query(
        self,
        *,
        dataset_id: str,
        question: str,
        conversation_id: str | None = None,
        request_id: str | None = None,
        run_mode: Literal["interactive", "eval", "test"] = "interactive",
        llm_provider: str | None = None,
    ) -> PreparedRun:
        request_id = request_id or str(uuid4())
        resolved_provider = llm_provider or self.settings.llm_provider
        with self.metadata.session() as session:
            existing = session.scalar(select(QueryLog).where(QueryLog.request_id == request_id))
            if existing:
                config = self._config(existing.conversation_id or request_id, existing.request_id)
                if existing.result_json:
                    return PreparedRun(
                        state=None,
                        config=config,
                        cached_response=json.loads(existing.result_json),
                    )
                if existing.status == "pending_approval":
                    return PreparedRun(
                        state=None,
                        config=config,
                        cached_response=self._pending_response(
                            session, existing, self._checkpoint_state(config)
                        ),
                    )
                raise AppError(
                    "internal_error",
                    "A request with this ID is already processing.",
                    status_code=409,
                )

            dataset = session.get(Dataset, dataset_id)
            if dataset is None:
                raise AppError(
                    "dataset_not_found", "The selected dataset does not exist.", status_code=404
                )

            conversation: Conversation | None = None
            if run_mode == "interactive":
                if conversation_id:
                    conversation = session.get(Conversation, conversation_id)
                    if conversation is None:
                        raise AppError(
                            "dataset_not_found", "The conversation does not exist.", status_code=404
                        )
                    if conversation.dataset_id != dataset_id:
                        raise AppError(
                            "dataset_not_found",
                            "The conversation belongs to a different dataset.",
                            status_code=409,
                        )
                else:
                    conversation = Conversation(
                        title=question[:80] + ("..." if len(question) > 80 else ""),
                        dataset_id=dataset_id,
                    )
                    session.add(conversation)
                    session.flush()
                    conversation_id = conversation.id

            thread_id = conversation_id if conversation_id else request_id
            query_log = QueryLog(
                request_id=request_id,
                conversation_id=conversation_id,
                dataset_id=dataset_id,
                run_mode=run_mode,
                question=question,
                status="processing",
                llm_provider=resolved_provider,
            )
            session.add(query_log)
            session.flush()
            run = AgentRun(query_log_id=query_log.id, thread_id=thread_id, status="processing")
            session.add(run)
            session.flush()
            if conversation_id:
                session.add(
                    ConversationMessage(
                        conversation_id=conversation_id,
                        role="user",
                        content=question,
                        query_log_id=query_log.id,
                    )
                )
                if conversation:
                    conversation.updated_at = datetime.now(UTC)

            state: DataAnalysisState = {
                "request_id": request_id,
                "run_mode": run_mode,
                "conversation_id": conversation_id,
                "thread_id": thread_id,
                "dataset_id": dataset_id,
                "question": question,
                "response_language": detect_response_language(question),
                "active_analysis_question": question,
                "analysis_mode": "simple_query",
                "analysis_intent": None,
                "analysis_plan": None,
                "current_analysis_step_id": None,
                "evidence_by_step": {},
                "critic_result": None,
                "next_analysis_decision": None,
                "analysis_step_count": 0,
                "evidence_insufficient": False,
                "final_analysis": None,
                "supporting_charts": [],
                "tool_failures": 0,
                "decision_retries": 0,
                "conversation_history": [],
                "available_tables": [],
                "dataset_capability": {},
                "selected_tables": [],
                "selected_columns": [],
                "columns": [],
                "rows": [],
                "row_count": 0,
                "returned_row_count": 0,
                "is_truncated": False,
                "risk_level": "low",
                "risk_reasons": [],
                "requires_approval": False,
                "repair_attempts": 0,
                "validation_repair_attempts": 0,
                "execution_repair_attempts": 0,
                "repair_source": None,
                "grounding_repair_attempts": 0,
                "used_fallback": False,
                "llm_provider": resolved_provider,
                "query_log_id": query_log.id,
                "run_id": run.id,
                "status": "processing",
                "started_at_epoch_ms": time.time() * 1000,
                "events": [],
                "errors": [],
            }
        return PreparedRun(state=state, config=self._config(thread_id, request_id))

    @staticmethod
    def _config(thread_id: str, checkpoint_ns: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns},
            "recursion_limit": 100,
        }

    def _temporary_llm(
        self,
        request_id: str,
        deepseek_api_key: str | None,
        local_model: LocalModelConfig | None = None,
    ):
        if local_model and local_model.enabled:
            return self.llm_resolver.temporary(
                request_id,
                get_local_model_client(self.settings, local_model.base_url, local_model.model),
            )
        if not deepseek_api_key:
            return nullcontext()
        client = get_deepseek_client(self.settings, deepseek_api_key)
        return self.llm_resolver.temporary(request_id, client)

    def run_query(
        self,
        *,
        deepseek_api_key: str | None = None,
        local_model: LocalModelConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        request_id = kwargs.get("request_id") or str(uuid4())
        kwargs["request_id"] = request_id
        provider = (
            "local"
            if local_model and local_model.enabled
            else "deepseek"
            if deepseek_api_key
            else self.settings.llm_provider
        )
        with self._temporary_llm(request_id, deepseek_api_key, local_model):
            prepared = self.prepare_query(**kwargs, llm_provider=provider)
            if prepared.cached_response is not None:
                return prepared.cached_response
            try:
                result = self.graph.invoke(prepared.state, prepared.config)
            except AppError as exc:
                if local_model and local_model.enabled:
                    logger.exception("Local model request failed", exc_info=exc)
                self._mark_failed(prepared.state, exc.error_type, exc.message)
                raise
            except Exception:
                self._mark_failed(prepared.state)
                raise
            final = result.get("final_response") if isinstance(result, dict) else None
            if final:
                return final
            return self.pending_response_for_config(prepared.config, prepared.state)

    def stream_query(
        self,
        *,
        deepseek_api_key: str | None = None,
        local_model: LocalModelConfig | None = None,
        **kwargs: Any,
    ) -> Iterator[dict[str, Any]]:
        request_id = kwargs.get("request_id") or str(uuid4())
        kwargs["request_id"] = request_id
        provider = (
            "local"
            if local_model and local_model.enabled
            else "deepseek"
            if deepseek_api_key
            else self.settings.llm_provider
        )
        with self._temporary_llm(request_id, deepseek_api_key, local_model):
            prepared = self.prepare_query(**kwargs, llm_provider=provider)
            if prepared.cached_response is not None:
                yield {"event": "result", "data": prepared.cached_response}
                yield {"event": "done", "data": {}}
                return
            final_response: dict[str, Any] | None = None
            try:
                for chunk in self.graph.stream(
                    prepared.state,
                    prepared.config,
                    stream_mode=["custom", "updates"],
                ):
                    if not isinstance(chunk, tuple) or len(chunk) != 2:
                        continue
                    mode, data = chunk
                    if mode == "custom" and isinstance(data, dict) and data.get("kind") == "trace":
                        event = data["event"]
                        event_name = event.get("event_type", "node")
                        if event_name not in {
                            "run_started",
                            "approval_required",
                            "analysis_step_started",
                            "query_tool_called",
                            "evidence_created",
                            "critic_completed",
                            "analysis_decision",
                            "analysis_finished",
                            "final_synthesis_started",
                            "final_synthesis_completed",
                            "final_grounding_validated",
                            "supporting_charts_selected",
                        }:
                            event_name = "node"
                        yield {"event": event_name, "id": event.get("id"), "data": event}
                    elif mode == "updates" and isinstance(data, dict):
                        for update in data.values():
                            if isinstance(update, dict) and update.get("final_response"):
                                final_response = update["final_response"]
                if final_response is None:
                    final_response = self.pending_response_for_config(
                        prepared.config, prepared.state
                    )
                yield {"event": "result", "data": final_response}
                yield {"event": "done", "data": {}}
            except GeneratorExit:
                self._mark_failed(
                    prepared.state,
                    "internal_error",
                    "The client disconnected before the stream completed.",
                )
                return
            except AppError as exc:
                if local_model and local_model.enabled:
                    logger.exception("Local model request failed", exc_info=exc)
                self._mark_failed(prepared.state, exc.error_type, exc.message)
                yield {
                    "event": "error",
                    "data": {"type": exc.error_type, "message": exc.message},
                }
                yield {"event": "done", "data": {}}
            except Exception:
                self._mark_failed(prepared.state)
                yield {
                    "event": "error",
                    "data": {
                        "type": "internal_error",
                        "message": "The analysis stream ended unexpectedly.",
                    },
                }
                yield {"event": "done", "data": {}}

    def pending_response_for_config(
        self, config: dict[str, Any], initial_state: DataAnalysisState | None = None
    ) -> dict[str, Any]:
        configurable = config.get("configurable", {})
        request_id = configurable.get("checkpoint_ns")
        query_log_id = initial_state.get("query_log_id") if initial_state else None
        with self.metadata.session() as session:
            query_log = session.get(QueryLog, query_log_id) if query_log_id else None
            if query_log is None and request_id:
                query_log = session.scalar(
                    select(QueryLog).where(QueryLog.request_id == request_id)
                )
            if query_log is None:
                raise AppError("internal_error", "The interrupted query could not be recovered.")
            return self._pending_response(session, query_log, self._checkpoint_state(config))

    def _checkpoint_state(self, config: dict[str, Any]) -> DataAnalysisState | None:
        root_config = {
            **config,
            "configurable": {**config.get("configurable", {}), "checkpoint_ns": ""},
        }
        checkpoint = self.graph.checkpointer.get(root_config)
        values = checkpoint.get("channel_values") if checkpoint else None
        return values if isinstance(values, dict) else None

    def _pending_response(
        self,
        session: Any,
        query_log: QueryLog,
        checkpoint_state: DataAnalysisState | None = None,
    ) -> dict[str, Any]:
        approval = (
            session.get(ApprovalRequest, query_log.approval_id) if query_log.approval_id else None
        )
        trace = self._trace(session, query_log.id)
        analysis_intent_summary = self._event_payload(trace, "analysis_intent_created")
        checkpoint_state = checkpoint_state or {}
        analysis_mode = (
            "investigative_analysis"
            if analysis_intent_summary and analysis_intent_summary.get("needs_multi_step")
            else "simple_query"
        )
        return {
            "request_id": query_log.request_id,
            "conversation_id": query_log.conversation_id,
            "query_log_id": query_log.id,
            "status": "pending_approval",
            "question": query_log.question,
            "response_language": checkpoint_state.get("response_language")
            or detect_response_language(query_log.question),
            "rewritten_question": query_log.rewritten_question,
            "analysis_mode": checkpoint_state.get("analysis_mode", analysis_mode),
            "analysis_intent": checkpoint_state.get("analysis_intent"),
            "analysis_plan": checkpoint_state.get("analysis_plan"),
            "evidence": list(checkpoint_state.get("evidence_by_step", {}).values()),
            "critic_result": checkpoint_state.get("critic_result"),
            "analysis_step_count": checkpoint_state.get("analysis_step_count", 0),
            "evidence_insufficient": checkpoint_state.get("evidence_insufficient", False),
            "final_analysis": checkpoint_state.get("final_analysis"),
            "supporting_charts": checkpoint_state.get("supporting_charts", []),
            "clarification_question": None,
            "selected_tables": json.loads(query_log.selected_tables_json or "[]"),
            "selected_columns": json.loads(query_log.selected_columns_json or "[]"),
            "sql": query_log.normalized_sql or query_log.generated_sql,
            "safe_sql": query_log.safe_sql,
            "safety_reason": query_log.safety_reason,
            "risk_level": query_log.risk_level,
            "approval": {
                "id": approval.id,
                "risk_level": approval.risk_level,
                "reasons": json.loads(approval.reasons_json),
                "sql_preview": approval.sql_preview,
            }
            if approval
            else None,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "chart": None,
            "insight": None,
            "lineage": {
                "tables": json.loads(query_log.selected_tables_json or "[]"),
                "columns": json.loads(query_log.selected_columns_json or "[]"),
                "schema_hash": query_log.schema_hash,
            },
            "execution_time_ms": query_log.execution_time_ms,
            "trace": trace,
            "used_fallback": query_log.used_fallback,
            "error": None,
        }

    @staticmethod
    def _event_payload(trace: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
        for event in trace:
            if event.get("event_type") != event_type or not event.get("output_summary"):
                continue
            try:
                payload = json.loads(event["output_summary"])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                return payload
        return None

    @staticmethod
    def _trace(session: Any, query_log_id: str) -> list[dict[str, Any]]:
        events = list(
            session.scalars(
                select(AgentEvent)
                .where(AgentEvent.query_log_id == query_log_id)
                .order_by(AgentEvent.step_index, AgentEvent.created_at)
            )
        )
        return [
            {
                "id": event.id,
                "step_index": event.step_index,
                "node_name": event.node_name,
                "event_type": event.event_type,
                "status": event.status,
                "input_summary": event.input_summary,
                "output_summary": event.output_summary,
                "latency_ms": event.latency_ms,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ]

    def resume_approval(
        self,
        approval_id: str,
        *,
        approved: bool,
        note: str | None = None,
        deepseek_api_key: str | None = None,
        local_model: LocalModelConfig | None = None,
    ) -> dict[str, Any]:
        with self.metadata.session() as session:
            approval = session.get(ApprovalRequest, approval_id)
            if approval is None:
                raise AppError(
                    "approval_required", "The approval request does not exist.", status_code=404
                )
            query_log = session.get(QueryLog, approval.query_log_id)
            if query_log is None:
                raise AppError(
                    "internal_error", "The associated query no longer exists.", status_code=404
                )
            if approval.status != "pending":
                raise AppError(
                    "approval_rejected",
                    "This approval request has already been decided.",
                    status_code=409,
                )
            if query_log.result_json:
                return json.loads(query_log.result_json)
            uses_deepseek = query_log.llm_provider == "deepseek"
            uses_local_model = query_log.llm_provider == "local"
            if approved and uses_deepseek and not deepseek_api_key:
                raise AppError(
                    "llm_auth_error",
                    "Re-enter the temporary DeepSeek API key to approve this query.",
                    status_code=401,
                )
            if approved and uses_local_model and not (local_model and local_model.enabled):
                raise AppError(
                    "local_model_error",
                    "Re-enable the local model to approve and resume this query.",
                    status_code=400,
                )
            approval.status = "approved" if approved else "rejected"
            approval.decision_note = note
            approval.decided_at = datetime.now(UTC)
            query_log.status = "processing" if approved else "rejected"
            thread_id = approval.thread_id
            request_id = query_log.request_id
        config = self._config(thread_id, request_id)
        temporary_key = deepseek_api_key if uses_deepseek else None
        temporary_local_model = local_model if uses_local_model else None
        with self._temporary_llm(request_id, temporary_key, temporary_local_model):
            result = self.graph.invoke(Command(resume={"approved": approved, "note": note}), config)
        final = result.get("final_response") if isinstance(result, dict) else None
        if final:
            return final
        return self.pending_response_for_config(config)

    def _mark_failed(
        self,
        state: DataAnalysisState | None,
        error_type: str = "internal_error",
        error_message: str = "The graph failed unexpectedly.",
    ) -> None:
        if not state or not state.get("query_log_id"):
            return
        started_at = state.get("started_at_epoch_ms")
        elapsed = (
            max(0.0, time.time() * 1000 - started_at)
            if isinstance(started_at, int | float)
            else 0.0
        )
        with self.metadata.session() as session:
            query_log = session.get(QueryLog, state["query_log_id"])
            if query_log:
                query_log.status = "failed"
                query_log.error_type = error_type
                query_log.error_message = error_message
                query_log.execution_time_ms = elapsed
                query_log.completed_at = datetime.now(UTC)
            if state.get("run_id"):
                run = session.get(AgentRun, state["run_id"])
                if run:
                    run.status = "failed"
                    run.total_latency_ms = elapsed
                    run.completed_at = datetime.now(UTC)
                    run.completed_at = datetime.now(UTC)
