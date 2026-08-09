from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.data.schema_reader import preview_table
from app.data.seed import BUILTINS
from app.models import Dataset


def resolve_dataset_path(dataset: Dataset, settings: Settings) -> Path:
    path = Path(dataset.db_path).resolve()
    root = settings.datasets_dir.resolve()
    if path.parent != root or path in {
        settings.app_db_path.resolve(),
        settings.checkpoint_db_path.resolve(),
    }:
        raise AppError(
            "dataset_not_found", "Dataset storage could not be resolved.", status_code=404
        )
    if not path.exists() or path.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}:
        raise AppError("dataset_not_found", "Dataset storage is unavailable.", status_code=404)
    return path


def dataset_summary(dataset: Dataset) -> dict[str, Any]:
    tables = json.loads(dataset.tables_json)
    schema = json.loads(dataset.schema_json)
    description = dataset.description
    source_filename: str | None = None
    sheet_name: str | None = None
    if dataset.source_type in {"csv_upload", "excel_upload"}:
        try:
            upload_metadata = json.loads(description)
        except (json.JSONDecodeError, TypeError):
            upload_metadata = None
        if isinstance(upload_metadata, dict) and upload_metadata.get("kind") == "upload":
            description = str(upload_metadata.get("summary") or "Uploaded dataset.")
            source_filename = upload_metadata.get("source_filename")
            sheet_name = upload_metadata.get("sheet_name")
    return {
        "id": dataset.id,
        "name": dataset.name,
        "description": description,
        "source_type": dataset.source_type,
        "source_filename": source_filename,
        "sheet_name": sheet_name,
        "tables": tables,
        "table_count": len(tables),
        "column_count": sum(len(value.get("columns", [])) for value in schema.values()),
        "row_count": dataset.row_count,
        "is_builtin": dataset.is_builtin,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
        "suggested_questions": list(BUILTINS.get(dataset.id).suggestions)
        if dataset.id in BUILTINS
        else _upload_suggestions(schema),
    }


def dataset_detail(dataset: Dataset, settings: Settings) -> dict[str, Any]:
    summary = dataset_summary(dataset)
    tables = json.loads(dataset.tables_json)
    schema = json.loads(dataset.schema_json)
    path = resolve_dataset_path(dataset, settings)
    preview = preview_table(path, tables[0], 10) if tables else []
    if tables:
        sensitive = {
            column["name"]
            for column in schema.get(tables[0], {}).get("columns", [])
            if column.get("sensitive")
        }
        for row in preview:
            for column in sensitive:
                if row.get(column) is not None:
                    row[column] = "[REDACTED]"
    summary.update(
        {
            "schema": schema,
            "column_mapping": json.loads(dataset.column_mapping_json),
            "preview": preview,
        }
    )
    return summary


def list_datasets(session: Session) -> list[Dataset]:
    return list(
        session.scalars(select(Dataset).order_by(Dataset.is_builtin.desc(), Dataset.created_at))
    )


def _upload_suggestions(schema: dict[str, Any]) -> list[str]:
    if not schema:
        return []
    table = next(iter(schema.values()))
    columns = [column["name"] for column in table.get("columns", [])]
    suggestions = ["How many rows are in this dataset?"]
    numeric = [
        column["name"]
        for column in table.get("columns", [])
        if column.get("type", "").upper() in {"INTEGER", "REAL", "FLOAT", "NUMERIC"}
    ]
    if numeric:
        suggestions.append(f"What is the average {numeric[0]}?")
    if columns:
        suggestions.append(f"Show the distribution of {columns[0]}.")
    return suggestions
