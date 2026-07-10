from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.agent.service import QueryService
from app.core.db import MetadataDatabase
from app.evals.metrics import assertion_passed, average, p95, rate
from app.models import Conversation, EvalCaseResult, EvalRun
from app.schemas.eval import EvalCaseDefinition

EVAL_DATASET_PATH = Path(__file__).with_name("dataset.json")


def load_eval_cases() -> list[EvalCaseDefinition]:
    raw = json.loads(EVAL_DATASET_PATH.read_text(encoding="utf-8"))
    return [EvalCaseDefinition.model_validate(case) for case in raw]


class EvalRunner:
    def __init__(self, metadata: MetadataDatabase, query_service: QueryService) -> None:
        self.metadata = metadata
        self.query_service = query_service

    def run(self) -> EvalRun:
        cases = load_eval_cases()
        outcomes: list[dict[str, Any]] = []
        for case in cases:
            conversation_id = self._prepare_follow_up(case)
            response = self.query_service.run_query(
                dataset_id=case.dataset_id,
                question=case.question,
                conversation_id=conversation_id,
                request_id=f"eval-{case.id}-{uuid4()}",
                run_mode="eval",
            )
            outcome = self._evaluate(case, response)
            outcomes.append(outcome)
            if conversation_id:
                with self.metadata.session() as session:
                    conversation = session.get(Conversation, conversation_id)
                    if conversation:
                        session.delete(conversation)

        latencies = [
            float(outcome["response"].get("execution_time_ms", 0.0)) for outcome in outcomes
        ]
        assertion_outcomes = [
            outcome["assertion_ok"] for outcome in outcomes if outcome["has_assertion"]
        ]
        table_outcomes = [
            outcome["tables_ok"] for outcome in outcomes if outcome["has_expected_tables"]
        ]
        dangerous = [
            outcome["blocked_ok"] for outcome in outcomes if outcome["case"].should_be_blocked
        ]
        approval = [
            outcome["approval_ok"]
            for outcome in outcomes
            if outcome["case"].should_require_approval
        ]
        clarification = [
            outcome["status_ok"]
            for outcome in outcomes
            if outcome["case"].expected_status == "needs_clarification"
        ]
        charts = [
            outcome["chart_ok"]
            for outcome in outcomes
            if outcome["case"].expected_chart_type is not None
        ]
        repairs = [outcome["repair_ok"] for outcome in outcomes if outcome["case"].expected_repair]
        passed = sum(outcome["passed"] for outcome in outcomes)
        eval_run = EvalRun(
            total_cases=len(outcomes),
            passed_cases=passed,
            failed_cases=len(outcomes) - passed,
            query_success_rate=rate(
                [outcome["response"].get("status") == "success" for outcome in outcomes]
            ),
            result_accuracy=rate(assertion_outcomes),
            table_selection_accuracy=rate(table_outcomes),
            sql_safety_accuracy=rate([outcome["blocked_ok"] for outcome in outcomes]),
            dangerous_sql_block_rate=rate(dangerous),
            approval_accuracy=rate(approval),
            clarification_accuracy=rate(clarification),
            chart_selection_accuracy=rate(charts),
            repair_success_rate=rate(repairs),
            fallback_rate=rate(
                [bool(outcome["response"].get("used_fallback")) for outcome in outcomes]
            ),
            average_latency_ms=average(latencies),
            p95_latency_ms=p95(latencies),
        )
        with self.metadata.session() as session:
            session.add(eval_run)
            session.flush()
            for outcome in outcomes:
                case = outcome["case"]
                response = outcome["response"]
                session.add(
                    EvalCaseResult(
                        eval_run_id=eval_run.id,
                        case_id=case.id,
                        category=case.category,
                        passed=outcome["passed"],
                        status=response.get("status", "failed"),
                        generated_sql=response.get("sql"),
                        actual_tables_json=json.dumps(response.get("selected_tables", [])),
                        actual_chart_type=(response.get("chart") or {}).get("type"),
                        expected_json=json.dumps(
                            {
                                "status": case.expected_status,
                                "tables": case.expected_tables,
                                "chart_type": case.expected_chart_type,
                                "approval": case.should_require_approval,
                                "blocked": case.should_be_blocked,
                            }
                        ),
                        actual_json=json.dumps(
                            {
                                "status": response.get("status"),
                                "tables": response.get("selected_tables", []),
                                "chart_type": (response.get("chart") or {}).get("type"),
                                "row_count": response.get("row_count", 0),
                            }
                        ),
                        failure_reasons_json=json.dumps(outcome["failure_reasons"]),
                        latency_ms=float(response.get("execution_time_ms", 0.0)),
                    )
                )
            session.flush()
            eval_run_id = eval_run.id
        with self.metadata.session() as session:
            return session.scalar(select(EvalRun).where(EvalRun.id == eval_run_id))

    def _prepare_follow_up(self, case: EvalCaseDefinition) -> str | None:
        if not case.setup_question:
            return None
        with self.metadata.session() as session:
            conversation = Conversation(
                dataset_id=case.dataset_id,
                title=f"Eval follow-up: {case.id}",
            )
            session.add(conversation)
            session.flush()
            conversation_id = conversation.id
        self.query_service.run_query(
            dataset_id=case.dataset_id,
            question=case.setup_question,
            conversation_id=conversation_id,
            request_id=f"eval-setup-{case.id}-{uuid4()}",
            run_mode="eval",
        )
        return conversation_id

    @staticmethod
    def _evaluate(case: EvalCaseDefinition, response: dict[str, Any]) -> dict[str, Any]:
        status = response.get("status")
        actual_tables = set(response.get("selected_tables", []))
        expected_tables = set(case.expected_tables)
        selected_columns = " ".join(response.get("selected_columns", [])).lower()
        status_ok = status == case.expected_status
        tables_ok = not expected_tables or expected_tables.issubset(actual_tables)
        columns_ok = not case.expected_columns_any or any(
            column.lower() in selected_columns for column in case.expected_columns_any
        )
        actual_chart = (response.get("chart") or {}).get("type")
        chart_ok = case.expected_chart_type is None or actual_chart == case.expected_chart_type
        blocked_ok = (status == "blocked") == case.should_be_blocked
        approval_ok = (status == "pending_approval") == case.should_require_approval
        assertion_ok = assertion_passed(case.result_assertion, response)
        repaired = any(
            event.get("node_name") == "repair_sql_node" for event in response.get("trace", [])
        )
        repair_ok = not case.expected_repair or repaired
        checks = {
            "status": status_ok,
            "tables": tables_ok,
            "columns": columns_ok,
            "chart": chart_ok,
            "blocked": blocked_ok,
            "approval": approval_ok,
            "result": assertion_ok,
            "repair": repair_ok,
        }
        failures = [name for name, passed in checks.items() if not passed]
        return {
            "case": case,
            "response": response,
            "passed": not failures,
            "failure_reasons": failures,
            "status_ok": status_ok,
            "tables_ok": tables_ok,
            "has_expected_tables": bool(expected_tables),
            "blocked_ok": blocked_ok,
            "approval_ok": approval_ok,
            "chart_ok": chart_ok,
            "assertion_ok": assertion_ok,
            "has_assertion": case.result_assertion is not None,
            "repair_ok": repair_ok,
        }
