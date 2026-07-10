from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.agent.service import QueryService
from app.api.dependencies import get_metadata, get_query_service
from app.core.db import MetadataDatabase
from app.core.errors import AppError
from app.evals.runner import EvalRunner
from app.models import EvalCaseResult, EvalRun
from app.schemas.eval import EvalRunResponse

router = APIRouter(prefix="/api/evals", tags=["evals"])


def _serialize(run: EvalRun, cases: list[EvalCaseResult] | None = None) -> dict:
    response = {
        "id": run.id,
        "total_cases": run.total_cases,
        "passed_cases": run.passed_cases,
        "failed_cases": run.failed_cases,
        "query_success_rate": run.query_success_rate,
        "result_accuracy": run.result_accuracy,
        "table_selection_accuracy": run.table_selection_accuracy,
        "sql_safety_accuracy": run.sql_safety_accuracy,
        "dangerous_sql_block_rate": run.dangerous_sql_block_rate,
        "approval_accuracy": run.approval_accuracy,
        "clarification_accuracy": run.clarification_accuracy,
        "chart_selection_accuracy": run.chart_selection_accuracy,
        "repair_success_rate": run.repair_success_rate,
        "fallback_rate": run.fallback_rate,
        "average_latency_ms": run.average_latency_ms,
        "p95_latency_ms": run.p95_latency_ms,
        "created_at": run.created_at,
        "cases": [],
    }
    if cases is not None:
        response["cases"] = [
            {
                "id": case.id,
                "case_id": case.case_id,
                "category": case.category,
                "passed": case.passed,
                "status": case.status,
                "generated_sql": case.generated_sql,
                "actual_tables": json.loads(case.actual_tables_json),
                "actual_chart_type": case.actual_chart_type,
                "expected": json.loads(case.expected_json),
                "actual": json.loads(case.actual_json),
                "failure_reasons": json.loads(case.failure_reasons_json),
                "latency_ms": case.latency_ms,
            }
            for case in cases
        ]
    return response


@router.post("/run", response_model=EvalRunResponse)
def run_eval(
    metadata: MetadataDatabase = Depends(get_metadata),
    service: QueryService = Depends(get_query_service),
) -> dict:
    run = EvalRunner(metadata, service).run()
    with metadata.session() as session:
        cases = list(
            session.scalars(
                select(EvalCaseResult)
                .where(EvalCaseResult.eval_run_id == run.id)
                .order_by(EvalCaseResult.case_id)
            )
        )
        return _serialize(run, cases)


@router.get("", response_model=list[EvalRunResponse])
def list_evals(metadata: MetadataDatabase = Depends(get_metadata)) -> list[dict]:
    with metadata.session() as session:
        runs = list(session.scalars(select(EvalRun).order_by(EvalRun.created_at.desc())))
        return [_serialize(run) for run in runs]


@router.get("/latest", response_model=EvalRunResponse)
def latest_eval(metadata: MetadataDatabase = Depends(get_metadata)) -> dict:
    with metadata.session() as session:
        run = session.scalar(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(1))
        if run is None:
            raise AppError("dataset_not_found", "No evaluation has been run yet.", status_code=404)
        cases = list(
            session.scalars(
                select(EvalCaseResult)
                .where(EvalCaseResult.eval_run_id == run.id)
                .order_by(EvalCaseResult.case_id)
            )
        )
        return _serialize(run, cases)


@router.get("/{eval_run_id}", response_model=EvalRunResponse)
def eval_detail(eval_run_id: str, metadata: MetadataDatabase = Depends(get_metadata)) -> dict:
    with metadata.session() as session:
        run = session.get(EvalRun, eval_run_id)
        if run is None:
            raise AppError(
                "dataset_not_found", "The evaluation run does not exist.", status_code=404
            )
        cases = list(
            session.scalars(
                select(EvalCaseResult)
                .where(EvalCaseResult.eval_run_id == run.id)
                .order_by(EvalCaseResult.case_id)
            )
        )
        return _serialize(run, cases)
