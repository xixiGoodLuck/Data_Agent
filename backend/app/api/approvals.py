from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.agent.service import QueryService
from app.api.dependencies import get_metadata, get_query_service
from app.api.temporary_credentials import get_temporary_deepseek_key
from app.core.db import MetadataDatabase
from app.core.errors import AppError
from app.models import ApprovalRequest, QueryLog
from app.schemas.approval import ApprovalDecision, ApprovalResponse
from app.schemas.query import QueryResponse

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _serialize(approval: ApprovalRequest, question: str | None) -> dict:
    return {
        "id": approval.id,
        "query_log_id": approval.query_log_id,
        "thread_id": approval.thread_id,
        "question": question,
        "risk_level": approval.risk_level,
        "reasons": json.loads(approval.reasons_json),
        "sql_preview": approval.sql_preview,
        "selected_tables": json.loads(approval.selected_tables_json),
        "selected_columns": json.loads(approval.selected_columns_json),
        "status": approval.status,
        "decision_note": approval.decision_note,
        "created_at": approval.created_at,
        "decided_at": approval.decided_at,
    }


@router.get("", response_model=list[ApprovalResponse])
def list_approvals(
    status: str | None = Query(default=None),
    metadata: MetadataDatabase = Depends(get_metadata),
) -> list[dict]:
    with metadata.session() as session:
        statement = (
            select(ApprovalRequest, QueryLog.question)
            .join(QueryLog, QueryLog.id == ApprovalRequest.query_log_id)
            .order_by(ApprovalRequest.created_at.desc())
        )
        if status:
            statement = statement.where(ApprovalRequest.status == status)
        return [_serialize(approval, question) for approval, question in session.execute(statement)]


@router.get("/{approval_id}", response_model=ApprovalResponse)
def approval_detail(approval_id: str, metadata: MetadataDatabase = Depends(get_metadata)) -> dict:
    with metadata.session() as session:
        row = session.execute(
            select(ApprovalRequest, QueryLog.question)
            .join(QueryLog, QueryLog.id == ApprovalRequest.query_log_id)
            .where(ApprovalRequest.id == approval_id)
        ).one_or_none()
        if row is None:
            raise AppError(
                "approval_required", "The approval request does not exist.", status_code=404
            )
        return _serialize(row[0], row[1])


@router.post("/{approval_id}/approve", response_model=QueryResponse)
def approve(
    approval_id: str,
    payload: ApprovalDecision,
    service: QueryService = Depends(get_query_service),
    deepseek_api_key: str | None = Depends(get_temporary_deepseek_key),
) -> dict:
    return service.resume_approval(
        approval_id,
        approved=True,
        note=payload.note,
        deepseek_api_key=deepseek_api_key,
        local_model=payload.local_model,
    )


@router.post("/{approval_id}/reject", response_model=QueryResponse)
def reject(
    approval_id: str,
    payload: ApprovalDecision,
    service: QueryService = Depends(get_query_service),
    deepseek_api_key: str | None = Depends(get_temporary_deepseek_key),
) -> dict:
    return service.resume_approval(
        approval_id,
        approved=False,
        note=payload.note,
        deepseek_api_key=deepseek_api_key,
        local_model=payload.local_model,
    )
