from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ColumnMapping(BaseModel):
    original: str
    sanitized: str


class DatasetSummary(BaseModel):
    id: str
    name: str
    description: str
    source_type: str
    tables: list[str]
    table_count: int
    column_count: int
    row_count: int
    is_builtin: bool
    created_at: datetime
    updated_at: datetime
    suggested_questions: list[str] = Field(default_factory=list)


class DatasetDetail(DatasetSummary):
    model_config = ConfigDict(populate_by_name=True)

    schema_data: dict[str, Any] = Field(alias="schema", serialization_alias="schema")
    column_mapping: list[ColumnMapping]
    preview: list[dict[str, Any]]
