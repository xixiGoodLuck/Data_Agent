from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    dataset_id: str
    title: str | None = Field(default=None, max_length=240)


class ConversationMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    query_log_id: str | None
    created_at: datetime


class ConversationSummary(BaseModel):
    id: str
    title: str
    dataset_id: str
    dataset_name: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessageResponse] = Field(default_factory=list)
