from __future__ import annotations

from typing import Any

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp


class SqlValidationResult(BaseModel):
    safe: bool
    normalized_sql: str | None = None
    reason_code: str | None = None
    reason: str | None = None
    referenced_tables: list[str] = Field(default_factory=list)
    referenced_columns: list[str] = Field(default_factory=list)


FORBIDDEN_NODE_NAMES = {
    "Alter",
    "Analyze",
    "Attach",
    "Command",
    "Copy",
    "Create",
    "Delete",
    "Detach",
    "Drop",
    "Execute",
    "Insert",
    "LoadData",
    "Lock",
    "Merge",
    "Pragma",
    "Replace",
    "Transaction",
    "TruncateTable",
    "Update",
    "Use",
    "Vacuum",
}
FORBIDDEN_FUNCTIONS = {
    "load_extension",
    "readfile",
    "writefile",
    "edit",
    "fts3_tokenizer",
}
INTERNAL_TABLE_PREFIXES = ("sqlite_", "pragma_")


def _outside_string_text(sql: str) -> str:
    output: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote:
            output.append(" ")
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    output.append(" ")
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            output.append(" ")
        else:
            output.append(char)
        index += 1
    return "".join(output)


def _blocked(code: str, message: str) -> SqlValidationResult:
    return SqlValidationResult(safe=False, reason_code=code, reason=message)


def _column_catalog(schema: dict[str, Any]) -> dict[str, set[str]]:
    return {
        table.lower(): {column["name"].lower() for column in details.get("columns", [])}
        for table, details in schema.items()
    }


def validate_sql(
    sql: str | None,
    *,
    allowed_tables: list[str],
    schema: dict[str, Any],
    max_rows: int = 100,
    max_ast_nodes: int = 500,
) -> SqlValidationResult:
    if not sql or not sql.strip():
        return _blocked("empty_sql", "No SQL statement was generated.")

    cleaned = sql.strip()
    outside = _outside_string_text(cleaned)
    if "--" in outside or "/*" in outside or "*/" in outside:
        return _blocked("comments_forbidden", "SQL comments are not allowed.")
    if cleaned.endswith(";") and outside.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
        outside = _outside_string_text(cleaned)
    if ";" in outside:
        return _blocked("multiple_statements", "Only one SQL statement is allowed.")

    try:
        parsed_statements = sqlglot.parse(cleaned, read="sqlite")
    except sqlglot.errors.ParseError:
        return _blocked("sql_parse_error", "The SQL could not be parsed in SQLite dialect.")
    if len(parsed_statements) != 1 or parsed_statements[0] is None:
        return _blocked("multiple_statements", "Only one SQL statement is allowed.")
    expression = parsed_statements[0]
    nodes = list(expression.walk())
    if len(nodes) > max_ast_nodes:
        return _blocked("query_too_complex", "The SQL exceeds the allowed complexity.")
    if any(type(node).__name__ in FORBIDDEN_NODE_NAMES for node in nodes):
        return _blocked("write_operation", "Only read-only SELECT queries are allowed.")
    if not isinstance(expression, (exp.Select, exp.SetOperation)):
        return _blocked("not_select", "The final SQL operation must be SELECT.")

    for function in expression.find_all(exp.Func):
        function_name = (
            function.name.lower()
            if isinstance(function, exp.Anonymous)
            else function.sql_name().lower()
        )
        if function_name in FORBIDDEN_FUNCTIONS:
            return _blocked("forbidden_function", "The SQL uses a forbidden SQLite function.")

    cte_names = {cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)}
    table_nodes = list(expression.find_all(exp.Table))
    table_aliases: dict[str, str] = {}
    referenced_tables: list[str] = []
    for table_node in table_nodes:
        table_name = table_node.name.lower()
        if table_name in cte_names:
            table_aliases[table_node.alias_or_name.lower()] = "__cte__"
            table_aliases[table_name] = "__cte__"
            continue
        if table_name.startswith(INTERNAL_TABLE_PREFIXES):
            return _blocked("internal_table", "SQLite internal tables are not accessible.")
        if table_node.db or table_node.catalog:
            return _blocked("qualified_database", "Cross-database references are not allowed.")
        if table_name not in referenced_tables:
            referenced_tables.append(table_name)
        table_aliases[table_node.alias_or_name.lower()] = table_name
        table_aliases[table_name] = table_name

    allowed = {table.lower() for table in allowed_tables}
    if not referenced_tables:
        return _blocked("missing_table", "The SQL does not reference a dataset table.")
    if not set(referenced_tables).issubset(allowed):
        return _blocked("unknown_table", "The SQL references a table outside the selected schema.")

    catalog = _column_catalog(schema)
    select_aliases = {item.alias.lower() for item in expression.find_all(exp.Alias) if item.alias}
    referenced_columns: list[str] = []
    for column in expression.find_all(exp.Column):
        name = column.name.lower()
        if name == "*":
            continue
        qualifier = column.table.lower() if column.table else ""
        if qualifier in cte_names:
            continue
        if qualifier:
            table_name = table_aliases.get(qualifier)
            if table_name == "__cte__":
                continue
            if table_name is None or name not in catalog.get(table_name, set()):
                return _blocked("unknown_column", "The SQL references an unknown column.")
            qualified = f"{table_name}.{name}"
        else:
            matching = [table for table in referenced_tables if name in catalog.get(table, set())]
            if not matching and name not in select_aliases:
                return _blocked("unknown_column", "The SQL references an unknown column.")
            qualified = f"{matching[0]}.{name}" if len(matching) == 1 else name
        if qualified not in referenced_columns:
            referenced_columns.append(qualified)

    normalized = expression.copy()
    limit = normalized.args.get("limit")
    limit_value = max_rows
    if limit is not None and limit.expression is not None:
        try:
            requested = int(limit.expression.name)
            if requested > 0:
                limit_value = min(requested, max_rows)
        except (TypeError, ValueError):
            limit_value = max_rows
    normalized.set("limit", exp.Limit(expression=exp.Literal.number(limit_value)))

    return SqlValidationResult(
        safe=True,
        normalized_sql=normalized.sql(dialect="sqlite"),
        referenced_tables=referenced_tables,
        referenced_columns=referenced_columns,
    )
