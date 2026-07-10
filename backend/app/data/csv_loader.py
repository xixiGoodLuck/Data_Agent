from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.data.schema_reader import inspect_database
from app.models import Dataset

SQL_RESERVED = {
    "select",
    "from",
    "where",
    "group",
    "order",
    "limit",
    "table",
    "index",
    "join",
    "by",
    "as",
    "and",
    "or",
}


def sanitize_column_names(headers: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    used: dict[str, int] = {}
    sanitized: list[str] = []
    mapping: list[dict[str, str]] = []
    for index, original in enumerate(headers, start=1):
        base = re.sub(r"[^a-zA-Z0-9_]+", "_", original.strip()).strip("_").lower()
        if not base:
            base = f"column_{index}"
        if base[0].isdigit():
            base = f"column_{base}"
        if base in SQL_RESERVED or base.startswith("sqlite_"):
            base = f"column_{base}"
        count = used.get(base, 0) + 1
        used[base] = count
        name = base if count == 1 else f"{base}_{count}"
        while name in sanitized:
            count += 1
            used[base] = count
            name = f"{base}_{count}"
        sanitized.append(name)
        mapping.append({"original": original, "sanitized": name})
    return sanitized, mapping


def _looks_like_header(headers: list[str], rows: list[list[str]]) -> bool:
    if not headers or all(not item.strip() for item in headers):
        return False
    if not rows:
        return True
    numeric_header = all(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", item.strip()) for item in headers)
    return not numeric_header


def _column_type(values: pd.Series) -> tuple[str, bool]:
    clean = values.astype(str).str.strip()
    nonempty = clean[clean != ""]
    if nonempty.empty:
        return "TEXT", False
    integer_pattern = nonempty.str.fullmatch(r"[-+]?(?:0|[1-9]\d*)")
    if bool(integer_pattern.all()):
        return "INTEGER", False
    real_pattern = nonempty.str.fullmatch(r"[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?")
    if bool(real_pattern.all()):
        return "REAL", False
    date_pattern = nonempty.str.fullmatch(
        r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?:[T ][0-2]\d:[0-5]\d(?::[0-5]\d)?)?"
    )
    return "TEXT", bool(date_pattern.all())


def ingest_csv(
    *,
    session: Session,
    settings: Settings,
    filename: str,
    content: bytes,
) -> Dataset:
    if not filename.lower().endswith(".csv"):
        raise AppError("invalid_upload", "Only .csv files are accepted.")
    if not content:
        raise AppError("invalid_upload", "The uploaded file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise AppError("invalid_upload", "The upload exceeds the 10 MB limit.", status_code=413)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("invalid_upload", "The CSV must use UTF-8 encoding.") from exc

    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        raw_rows = list(reader)
    except csv.Error as exc:
        raise AppError("invalid_upload", "The CSV structure is malformed.") from exc
    if not raw_rows:
        raise AppError("invalid_upload", "The uploaded file is empty.")
    headers = raw_rows[0]
    rows = raw_rows[1:]
    if len(headers) > settings.max_upload_columns:
        raise AppError("invalid_upload", "The CSV has more than 100 columns.")
    if not rows or all(all(not cell.strip() for cell in row) for row in rows):
        raise AppError("invalid_upload", "The CSV contains no data rows.")
    if len(rows) > settings.max_upload_rows:
        raise AppError("invalid_upload", "The CSV has more than 100,000 rows.", status_code=413)
    if not _looks_like_header(headers, rows):
        raise AppError("invalid_upload", "The CSV appears to be missing a header row.")
    if any(len(row) != len(headers) for row in rows):
        raise AppError("invalid_upload", "Every CSV row must have the same number of columns.")

    columns, mapping = sanitize_column_names(headers)
    frame = pd.DataFrame(rows, columns=columns)
    date_like: dict[str, bool] = {}
    sql_types: dict[str, str] = {}
    for column in columns:
        sql_type, is_date = _column_type(frame[column])
        sql_types[column] = sql_type
        date_like[column] = is_date
        if sql_type == "INTEGER":
            frame[column] = pd.to_numeric(frame[column].replace("", None), errors="raise").astype(
                "Int64"
            )
        elif sql_type == "REAL":
            frame[column] = pd.to_numeric(frame[column].replace("", None), errors="raise")
        else:
            frame[column] = frame[column].replace("", None)

    settings.ensure_runtime_dirs()
    dataset_id = str(uuid4())
    db_path = (settings.datasets_dir / f"{dataset_id}.sqlite3").resolve()
    upload_path = (settings.uploads_dir / f"{dataset_id}.csv").resolve()
    try:
        upload_path.write_bytes(content)
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            frame.to_sql("data", connection, if_exists="fail", index=False)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        schema = inspect_database(db_path)
        for column in schema["data"]["columns"]:
            column["date_like"] = date_like[column["name"]]
            column["type"] = sql_types[column["name"]]
        display_stem = Path(filename.replace("\\", "/")).name.rsplit(".", 1)[0]
        display_name = re.sub(r"[\x00-\x1f\x7f]+", "", display_stem).strip()[:120]
        dataset = Dataset(
            id=dataset_id,
            name=display_name or "Uploaded dataset",
            description=f"Uploaded CSV with {len(frame)} rows and {len(columns)} columns.",
            source_type="csv_upload",
            db_path=str(db_path),
            tables_json='["data"]',
            schema_json=json.dumps(schema),
            column_mapping_json=json.dumps(mapping),
            row_count=len(frame),
            is_builtin=False,
        )
        session.add(dataset)
        session.flush()
        return dataset
    except Exception:
        db_path.unlink(missing_ok=True)
        upload_path.unlink(missing_ok=True)
        raise


def delete_uploaded_dataset(dataset: Dataset, settings: Settings) -> None:
    if dataset.is_builtin or dataset.source_type != "csv_upload":
        raise AppError("invalid_upload", "Built-in datasets cannot be deleted.", status_code=409)
    db_path = Path(dataset.db_path).resolve()
    if db_path.parent != settings.datasets_dir.resolve():
        raise AppError("invalid_upload", "Dataset storage path is invalid.")
    db_path.unlink(missing_ok=True)
    (settings.uploads_dir / f"{dataset.id}.csv").resolve().unlink(missing_ok=True)
