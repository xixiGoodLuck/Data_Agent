from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.service import QueryService
from app.api.dependencies import get_query_service
from app.api.temporary_credentials import get_temporary_deepseek_key
from app.schemas.query import QueryRequest, QueryResponse

router = APIRouter(prefix="/api/query", tags=["query"])


@router.post("", response_model=QueryResponse)
def query(
    payload: QueryRequest,
    service: QueryService = Depends(get_query_service),
    deepseek_api_key: str | None = Depends(get_temporary_deepseek_key),
) -> dict:
    return service.run_query(
        dataset_id=payload.dataset_id,
        conversation_id=payload.conversation_id,
        question=payload.question,
        request_id=payload.request_id,
        run_mode="interactive",
        deepseek_api_key=deepseek_api_key,
    )


def _sse(
    service: QueryService, payload: QueryRequest, deepseek_api_key: str | None
) -> Iterator[str]:
    for item in service.stream_query(
        dataset_id=payload.dataset_id,
        conversation_id=payload.conversation_id,
        question=payload.question,
        request_id=payload.request_id,
        run_mode="interactive",
        deepseek_api_key=deepseek_api_key,
    ):
        lines = []
        if item.get("id"):
            lines.append(f"id: {item['id']}")
        lines.append(f"event: {item['event']}")
        lines.append("data: " + json.dumps(item.get("data", {}), ensure_ascii=False, default=str))
        yield "\n".join(lines) + "\n\n"


@router.post("/stream")
def query_stream(
    payload: QueryRequest,
    service: QueryService = Depends(get_query_service),
    deepseek_api_key: str | None = Depends(get_temporary_deepseek_key),
) -> StreamingResponse:
    return StreamingResponse(
        _sse(service, payload, deepseek_api_key),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
