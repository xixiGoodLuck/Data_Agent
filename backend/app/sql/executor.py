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
            rows = [
                {key: _json_value(row[key]) for key in row.keys()} for row in fetched[:max_rows]
            ]
            columns = [description[0] for description in cursor.description or []]
        return QueryExecutionResult(
            success=True,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )
    except sqlite3.OperationalError as exc:
        message = str(exc).lower()
        timed_out = "interrupted" in message or time.perf_counter() > deadline
        repairable = any(
            marker in message
            for marker in (
                "no such function",
                "ambiguous column",
                "no such column",
                "misuse of aggregate",
            )
        )
        return QueryExecutionResult(
            success=False,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            error_type="query_timeout" if timed_out else "query_execution_error",
            error_message="The query timed out."
            if timed_out
            else "SQLite could not execute the validated query.",
            repairable=repairable and not timed_out,
        )
    except sqlite3.DatabaseError:
        return QueryExecutionResult(
            success=False,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            error_type="query_execution_error",
            error_message="SQLite could not execute the validated query.",
        )
