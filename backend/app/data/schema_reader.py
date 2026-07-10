from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


def inspect_database(
    path: Path,
    *,
    selected_tables: list[str] | None = None,
    sensitive_columns: set[str] | None = None,
    sample_limit: int = 3,
) -> dict[str, Any]:
    sensitive_columns = sensitive_columns or set()
    result: dict[str, Any] = {}
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        available = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        tables = selected_tables or available
        for table in tables:
            if table not in available:
                continue
            columns = []
            for row in connection.execute(f'PRAGMA table_info("{table}")'):
                qualified = f"{table}.{row[1]}"
                columns.append(
                    {
                        "name": row[1],
                        "type": row[2] or "TEXT",
                        "nullable": not bool(row[3]),
                        "default": row[4],
                        "primary_key": bool(row[5]),
                        "sensitive": qualified in sensitive_columns,
                    }
                )
            foreign_keys = [
                {
                    "from_column": row[3],
                    "to_table": row[2],
                    "to_column": row[4],
                }
                for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')
            ]
            samples = []
            if sample_limit:
                cursor = connection.execute(f'SELECT * FROM "{table}" LIMIT ?', (sample_limit,))
                for row in cursor.fetchall():
                    item = dict(row)
                    for name in list(item):
                        if f"{table}.{name}" in sensitive_columns and item[name] is not None:
                            item[name] = "[REDACTED]"
                    samples.append(item)
            result[table] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "sample_rows": samples,
            }
    return result


def schema_hash(schema: dict[str, Any]) -> str:
    structural = {
        table: {
            "columns": [
                {
                    "name": column["name"],
                    "type": column["type"],
                    "primary_key": column["primary_key"],
                    "sensitive": column.get("sensitive", False),
                }
                for column in details["columns"]
            ],
            "foreign_keys": details["foreign_keys"],
        }
        for table, details in schema.items()
    }
    payload = json.dumps(structural, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compact_schema_context(schema: dict[str, Any]) -> str:
    chunks: list[str] = []
    for table, details in schema.items():
        column_text = ", ".join(
            f"{column['name']} {column['type']}"
            + (" [sensitive]" if column.get("sensitive") else "")
            for column in details["columns"]
        )
        chunks.append(f"TABLE {table}: {column_text}")
        for fk in details["foreign_keys"]:
            chunks.append(f"FK {table}.{fk['from_column']} -> {fk['to_table']}.{fk['to_column']}")
        if details.get("sample_rows"):
            chunks.append(
                "SAFE SAMPLES: "
                + json.dumps(details["sample_rows"], ensure_ascii=True, default=str)
            )
    return "\n".join(chunks)


def preview_table(path: Path, table: str, limit: int = 10) -> list[dict[str, Any]]:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        available = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if table not in available:
            return []
        return [
            dict(row) for row in connection.execute(f'SELECT * FROM "{table}" LIMIT ?', (limit,))
        ]
