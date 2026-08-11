from __future__ import annotations

import math
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class QueryExecutionResult(BaseModel):
    success: bool
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    returned_row_count: int = 0
    is_truncated: bool = False
    duration_ms: float = 0.0
    error_type: str | None = None
    error_message: str | None = None
    repairable: bool = False


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def execute_read_only(
    *,
    db_path: Path,
    sql: str,
    datasets_dir: Path,
    metadata_paths: set[Path],
    timeout_seconds: float = 2.0,
    max_rows: int = 100,
) -> QueryExecutionResult:
    started = time.perf_counter()
    resolved = db_path.resolve()
    if resolved.parent != datasets_dir.resolve() or resolved in {
        path.resolve() for path in metadata_paths
    }:
        return QueryExecutionResult(
            success=False,
            error_type="query_execution_error",
            error_message="Dataset storage is not accessible.",
        )
    deadline = started + timeout_seconds
    try:
        uri = f"{resolved.as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=timeout_seconds)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            connection.set_progress_handler(
                lambda: 1 if time.perf_counter() > deadline else 0, 1000
            )
            cursor = connection.execute(sql)
            fetched = cursor.fetchmany(max_rows + 1)
            is_truncated = len(fetched) > max_rows
            rows = [
                {key: _json_value(row[key]) for key in row.keys()} for row in fetched[:max_rows]
            ]
            columns = [description[0] for description in cursor.description or []]
        return QueryExecutionResult(
            success=True,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            returned_row_count=len(rows),
            is_truncated=is_truncated,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )
    except sqlite3.OperationalError as exc:
        message = str(exc).lower()
        timed_out = "interrupted" in message or time.perf_counter() > deadline
        if "no such function" in message:
            error_type = "unsupported_function"
        elif "no such column" in message:
            error_type = "unknown_column"
        elif "ambiguous column" in message or "order by term does not match" in message:
            error_type = "derived_scope_error"
        elif "misuse of aggregate" in message:
            error_type = "aggregate_fanout"
        else:
            error_type = "sqlite_execution_error"
        return QueryExecutionResult(
            success=False,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            error_type="query_timeout" if timed_out else error_type,
            error_message="The query timed out."
            if timed_out
            else "SQLite could not execute the validated query.",
            repairable=not timed_out,
        )
    except sqlite3.DatabaseError:
        return QueryExecutionResult(
            success=False,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            error_type="sqlite_execution_error",
            error_message="SQLite could not execute the validated query.",
        )
