from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, func, select

from app.api.dependencies import get_metadata
from app.core.db import MetadataDatabase
from app.core.errors import AppError
from app.models import AgentRun, Conversation, ConversationMessage, Dataset, QueryLog
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationMessageResponse,
    ConversationSummary,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _summary(conversation: Conversation, dataset_name: str | None, message_count: int) -> dict:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "dataset_id": conversation.dataset_id,
        "dataset_name": dataset_name,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "message_count": message_count,
    }


def _delete_conversation_records(session, conversation_ids: list[str], saver) -> None:
    if not conversation_ids:
        return
    thread_ids = set(
        session.scalars(
            select(AgentRun.thread_id)
            .join(QueryLog, QueryLog.id == AgentRun.query_log_id)
            .where(QueryLog.conversation_id.in_(conversation_ids))
        )
    )
    thread_ids.update(conversation_ids)
    session.execute(delete(QueryLog).where(QueryLog.conversation_id.in_(conversation_ids)))
    session.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
    session.flush()
    if hasattr(saver, "delete_thread"):
        for thread_id in thread_ids:
            saver.delete_thread(thread_id)


@router.post("", response_model=ConversationSummary, status_code=201)
def create_conversation(
    payload: ConversationCreate, metadata: MetadataDatabase = Depends(get_metadata)
) -> dict:
    with metadata.session() as session:
        dataset = session.get(Dataset, payload.dataset_id)
        if dataset is None:
            raise AppError(
                "dataset_not_found", "The selected dataset does not exist.", status_code=404
            )
        conversation = Conversation(
            title=(payload.title or "New analysis")[:240], dataset_id=payload.dataset_id
        )
        session.add(conversation)
        session.flush()
        return _summary(conversation, dataset.name, 0)


@router.get("", response_model=list[ConversationSummary])
def list_conversations(metadata: MetadataDatabase = Depends(get_metadata)) -> list[dict]:
    with metadata.session() as session:
        message_count = (
            select(
                ConversationMessage.conversation_id,
                func.count(ConversationMessage.id).label("message_count"),
            )
            .group_by(ConversationMessage.conversation_id)
            .subquery()
        )
        rows = session.execute(
            select(Conversation, Dataset.name, func.coalesce(message_count.c.message_count, 0))
            .join(Dataset, Dataset.id == Conversation.dataset_id)
            .outerjoin(message_count, message_count.c.conversation_id == Conversation.id)
            .order_by(Conversation.updated_at.desc())
        ).all()
        return [_summary(conversation, name, count) for conversation, name, count in rows]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def conversation_detail(
    conversation_id: str, metadata: MetadataDatabase = Depends(get_metadata)
) -> dict:
    with metadata.session() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise AppError("dataset_not_found", "The conversation does not exist.", status_code=404)
        dataset = session.get(Dataset, conversation.dataset_id)
        messages = list(
            session.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation_id)
                .order_by(ConversationMessage.created_at)
            )
        )
        query_log_ids = [message.query_log_id for message in messages if message.query_log_id]
        query_results = {
            query_log.id: json.loads(query_log.result_json)
            for query_log in session.scalars(select(QueryLog).where(QueryLog.id.in_(query_log_ids)))
            if query_log.result_json
        }
        response = _summary(conversation, dataset.name if dataset else None, len(messages))
        response["messages"] = [
            {
                **ConversationMessageResponse.model_validate(message).model_dump(),
                "result": query_results.get(message.query_log_id),
            }
            for message in messages
        ]
        return response


@router.delete("")
def clear_conversations(
    request: Request,
    metadata: MetadataDatabase = Depends(get_metadata),
) -> dict[str, int | str]:
    with metadata.session() as session:
        conversation_ids = list(session.scalars(select(Conversation.id)))
        _delete_conversation_records(session, conversation_ids, request.app.state.checkpoint.saver)
    return {"status": "deleted", "deleted_count": len(conversation_ids)}


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    request: Request,
    metadata: MetadataDatabase = Depends(get_metadata),
) -> dict[str, str]:
    with metadata.session() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise AppError("dataset_not_found", "The conversation does not exist.", status_code=404)
        _delete_conversation_records(session, [conversation_id], request.app.state.checkpoint.saver)
    return {"status": "deleted", "conversation_id": conversation_id}
