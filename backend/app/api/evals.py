from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.agent.service import QueryService
from app.api.dependencies import get_metadata, get_query_service
from app.api.temporary_credentials import get_temporary_deepseek_key
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


def _serialize_with_cases(metadata: MetadataDatabase, run: EvalRun) -> dict:
    with metadata.session() as session:
        cases = list(
            session.scalars(
                select(EvalCaseResult)
                .where(EvalCaseResult.eval_run_id == run.id)
                .order_by(EvalCaseResult.case_id)
            )
        )
        return _serialize(run, cases)


@router.post("/run", response_model=EvalRunResponse)
def run_eval(
    metadata: MetadataDatabase = Depends(get_metadata),
    service: QueryService = Depends(get_query_service),
    deepseek_api_key: str | None = Depends(get_temporary_deepseek_key),
) -> dict:
    run = EvalRunner(metadata, service).run(deepseek_api_key=deepseek_api_key)
    return _serialize_with_cases(metadata, run)


def _format_sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: " + json.dumps(data, ensure_ascii=False, default=str) + "\n\n"


def _stream_eval(
    metadata: MetadataDatabase,
    service: QueryService,
    deepseek_api_key: str | None,
) -> Iterator[str]:
    events = EvalRunner(metadata, service).stream(deepseek_api_key=deepseek_api_key)
    try:
        for item in events:
            data = item.get("data", {})
            if item.get("event") == "result" and isinstance(data, EvalRun):
                data = _serialize_with_cases(metadata, data)
            yield _format_sse(str(item.get("event") or "message"), data)
        yield _format_sse("done", {})
    except AppError as exc:
        yield _format_sse(
            "error",
            {"type": exc.error_type, "message": exc.message},
        )
        yield _format_sse("done", {})
    except Exception:
        yield _format_sse(
            "error",
            {
                "type": "internal_error",
                "message": "The evaluation stream ended unexpectedly.",
            },
        )
        yield _format_sse("done", {})
    finally:
        events.close()


@router.post("/run/stream")
def run_eval_stream(
    metadata: MetadataDatabase = Depends(get_metadata),
    service: QueryService = Depends(get_query_service),
    deepseek_api_key: str | None = Depends(get_temporary_deepseek_key),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_eval(metadata, service, deepseek_api_key),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
