from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.agent.service import QueryService
from app.api.dependencies import get_metadata
from app.core.db import MetadataDatabase
from app.core.errors import AppError
from app.models import Dataset, QueryLog

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _serialize_log(log: QueryLog, dataset_name: str | None = None) -> dict[str, Any]:
    result = json.loads(log.result_json) if log.result_json else None
    return {
        "id": log.id,
        "request_id": log.request_id,
        "conversation_id": log.conversation_id,
        "dataset_id": log.dataset_id,
        "dataset_name": dataset_name,
        "run_mode": log.run_mode,
        "question": log.question,
        "rewritten_question": log.rewritten_question,
        "selected_tables": json.loads(log.selected_tables_json or "[]"),
        "selected_columns": json.loads(log.selected_columns_json or "[]"),
        "schema_hash": log.schema_hash,
        "generated_sql": log.generated_sql,
        "normalized_sql": log.normalized_sql,
        "status": log.status,
        "safe_sql": log.safe_sql,
        "safety_reason": log.safety_reason,
        "risk_level": log.risk_level,
        "approval_id": log.approval_id,
        "row_count": log.row_count,
        "chart_type": log.chart_type,
        "execution_time_ms": log.execution_time_ms,
        "llm_provider": log.llm_provider,
        "used_fallback": log.used_fallback,
        "error_type": log.error_type,
        "error_message": log.error_message,
        "lineage": result.get("lineage") if result else None,
        "created_at": log.created_at,
        "completed_at": log.completed_at,
    }


@router.get("")
def list_logs(
    dataset_id: str | None = None,
    status: str | None = None,
    run_mode: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    metadata: MetadataDatabase = Depends(get_metadata),
) -> dict[str, Any]:
    filters = []
    if dataset_id:
        filters.append(QueryLog.dataset_id == dataset_id)
    if status:
        filters.append(QueryLog.status == status)
    if run_mode:
        filters.append(QueryLog.run_mode == run_mode)
    if date_from:
        filters.append(QueryLog.created_at >= date_from)
    if date_to:
        filters.append(QueryLog.created_at <= date_to)
    with metadata.session() as session:
        total = session.scalar(select(func.count(QueryLog.id)).where(*filters)) or 0
        rows = session.execute(
            select(QueryLog, Dataset.name)
            .join(Dataset, Dataset.id == QueryLog.dataset_id)
            .where(*filters)
            .order_by(QueryLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {
            "items": [_serialize_log(log, name) for log, name in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


@router.get("/{query_log_id}")
def log_detail(
    query_log_id: str, metadata: MetadataDatabase = Depends(get_metadata)
) -> dict[str, Any]:
    with metadata.session() as session:
        row = session.execute(
            select(QueryLog, Dataset.name)
            .join(Dataset, Dataset.id == QueryLog.dataset_id)
            .where(QueryLog.id == query_log_id)
        ).one_or_none()
        if row is None:
            raise AppError("dataset_not_found", "The query log does not exist.", status_code=404)
        response = _serialize_log(row[0], row[1])
        response["result"] = json.loads(row[0].result_json) if row[0].result_json else None
        return response


@router.get("/{query_log_id}/events")
def log_events(
    query_log_id: str, metadata: MetadataDatabase = Depends(get_metadata)
) -> list[dict[str, Any]]:
    with metadata.session() as session:
        if session.get(QueryLog, query_log_id) is None:
            raise AppError("dataset_not_found", "The query log does not exist.", status_code=404)
        return QueryService._trace(session, query_log_id)
