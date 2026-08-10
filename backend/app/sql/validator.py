from __future__ import annotations

from itertools import combinations
from typing import Any

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope


class SqlValidationResult(BaseModel):
    safe: bool
    repairable: bool = False
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


def _has_nonunique_derived_self_join(
    expression: exp.Expression,
    *,
    schema: dict[str, Any],
) -> bool:
    target_select = (
        expression if isinstance(expression, exp.Select) else expression.find(exp.Select)
    )
    if target_select is None or not any(
        aggregate.find_ancestor(exp.Select) is target_select
        for aggregate in target_select.find_all(exp.AggFunc)
    ):
        return False
    outer_aliases = {
        table.alias_or_name.lower(): table.name.lower()
        for table in target_select.find_all(exp.Table)
        if table.find_ancestor(exp.Select) is target_select
    }
    for join in target_select.args.get("joins") or []:
        subquery = join.this
        if not isinstance(subquery, exp.Subquery):
            continue
        derived_alias = subquery.alias_or_name.lower()
        source_tables = {table.name.lower() for table in subquery.this.find_all(exp.Table)}
        on_expression = join.args.get("on")
        if not derived_alias or not source_tables or on_expression is None:
            continue
        derived_join_columns = {
            column.name.lower()
            for column in on_expression.find_all(exp.Column)
            if column.table.lower() == derived_alias
        }
        grouped_columns = {
            column.name.lower()
            for column in (subquery.this.args.get("group") or exp.Group()).find_all(exp.Column)
        }
        selected_names = {
            projection.alias_or_name.lower()
            for projection in subquery.this.expressions
            if projection.alias_or_name
        }
        unique_on_join = bool(grouped_columns) and grouped_columns.issubset(derived_join_columns)
        if subquery.this.args.get("distinct") and selected_names.issubset(derived_join_columns):
            unique_on_join = True
        for outer_alias, outer_table in outer_aliases.items():
            if outer_table not in source_tables:
                continue
            outer_join_columns = {
                column.name.lower()
                for column in on_expression.find_all(exp.Column)
                if column.table.lower() == outer_alias
            }
            primary_keys = {
                column["name"].lower()
                for column in schema.get(outer_table, {}).get("columns", [])
                if column.get("primary_key")
            }
            if primary_keys and primary_keys.issubset(outer_join_columns):
                unique_on_join = True
            if outer_join_columns and not unique_on_join:
                return True
    return False


def _has_flat_sibling_aggregate_fanout(
    expression: exp.Expression,
    *,
    schema: dict[str, Any],
    table_aliases: dict[str, str],
    referenced_tables: list[str],
) -> bool:
    catalog = _column_catalog(schema)
    derived_grains: dict[str, str] = {}
    for subquery in expression.find_all(exp.Subquery):
        alias = subquery.alias_or_name.lower()
        source_tables = {table.name.lower() for table in subquery.this.find_all(exp.Table)}
        if not alias or len(source_tables) != 1:
            continue
        source_table = next(iter(source_tables))
        grain = source_table
        group = subquery.this.args.get("group")
        grouped_columns = (
            {column.name.lower() for column in group.find_all(exp.Column)} if group else set()
        )
        for foreign_key in schema.get(source_table, {}).get("foreign_keys", []):
            if foreign_key.get("from_column", "").lower() in grouped_columns:
                grain = foreign_key.get("to_table", source_table).lower()
                break
        derived_grains[alias] = grain
    target_select = (
        expression if isinstance(expression, exp.Select) else expression.find(exp.Select)
    )
    aggregate_source_sets: list[set[str]] = []
    for aggregate in expression.find_all(exp.AggFunc):
        if aggregate.find_ancestor(exp.Select) is not target_select:
            continue
        if isinstance(aggregate, exp.Count) and aggregate.find(exp.Distinct) is not None:
            continue
        aggregate_tables: set[str] = set()
        for column in aggregate.find_all(exp.Column):
            qualifier = column.table.lower() if column.table else ""
            if qualifier:
                table_name = table_aliases.get(qualifier)
                if table_name == "__derived__":
                    table_name = derived_grains.get(qualifier)
            else:
                matching = [
                    table
                    for table in referenced_tables
                    if column.name.lower() in catalog.get(table, set())
                ]
                table_name = matching[0] if len(matching) == 1 else None
            if table_name and table_name != "__cte__":
                aggregate_tables.add(table_name)
        if aggregate_tables:
            aggregate_source_sets.append(aggregate_tables)
    all_aggregate_tables = set().union(*aggregate_source_sets) if aggregate_source_sets else set()
    parents_by_child = {
        table: {
            foreign_key.get("to_table", "").lower()
            for foreign_key in details.get("foreign_keys", [])
            if foreign_key.get("to_table")
        }
        for table, details in schema.items()
    }
    for left, right in combinations(sorted(all_aggregate_tables), 2):
        related = bool(
            parents_by_child.get(left, set()) & parents_by_child.get(right, set())
            or left in parents_by_child.get(right, set())
            or right in parents_by_child.get(left, set())
        )
        allocated_together = any(
            {left, right}.issubset(aggregate_tables) for aggregate_tables in aggregate_source_sets
        )
        if related and not allocated_together:
            return True
    return False


def _scope_unique_on(
    source: Scope | exp.Table,
    columns: set[str],
    *,
    schema: dict[str, Any],
) -> bool:
    if not columns:
        return False
    if isinstance(source, Scope):
        group = source.expression.args.get("group")
        group_keys = {
            item.alias_or_name.lower()
            for item in (group.expressions if group else [])
            if item.alias_or_name
        }
        return bool(group_keys) and group_keys.issubset(columns)
    primary_keys = {
        column["name"].lower()
        for column in schema.get(source.name.lower(), {}).get("columns", [])
        if column.get("primary_key")
    }
    return bool(primary_keys) and primary_keys.issubset(columns)


def _has_repeated_joined_measure(expression: exp.Expression, *, schema: dict[str, Any]) -> bool:
    for scope in traverse_scope(expression):
        selected_sources = {
            alias.lower(): source
            for alias, (_, source) in scope.selected_sources.items()
            if isinstance(source, Scope | exp.Table)
        }
        if len(selected_sources) < 2:
            continue
        join_columns: dict[str, set[str]] = {alias: set() for alias in selected_sources}
        for join in scope.expression.args.get("joins") or []:
            on_expression = join.args.get("on")
            if on_expression is None:
                continue
            for equality in on_expression.find_all(exp.EQ):
                for column in equality.find_all(exp.Column):
                    alias = column.table.lower()
                    if alias in join_columns:
                        join_columns[alias].add(column.name.lower())
        unique = {
            alias: _scope_unique_on(source, join_columns[alias], schema=schema)
            for alias, source in selected_sources.items()
        }
        if not any(unique.values()) or all(unique.values()):
            continue
        target_select = scope.expression
        for aggregate in target_select.find_all(exp.AggFunc):
            if aggregate.find_ancestor(exp.Select) is not target_select:
                continue
            if isinstance(aggregate, exp.Count) and aggregate.find(exp.Distinct) is not None:
                continue
            aliases = {
                column.table.lower() for column in aggregate.find_all(exp.Column) if column.table
            }
            if len(aliases) != 1:
                continue
            measure_alias = next(iter(aliases))
            if unique.get(measure_alias) and any(
                not is_unique for alias, is_unique in unique.items() if alias != measure_alias
            ):
                return True
    return False


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
    derived_columns: dict[str, set[str]] = {
        cte.alias_or_name.lower(): {
            projection.alias_or_name.lower()
            for projection in cte.this.expressions
            if projection.alias_or_name
        }
        for cte in expression.find_all(exp.CTE)
        if cte.alias_or_name and isinstance(cte.this, exp.Select)
    }
    table_nodes = list(expression.find_all(exp.Table))
    table_aliases: dict[str, str] = {}
    referenced_tables: list[str] = []
    for table_node in table_nodes:
        table_name = table_node.name.lower()
        if table_name in cte_names:
            table_aliases[table_node.alias_or_name.lower()] = "__cte__"
            table_aliases[table_name] = "__cte__"
            derived_columns[table_node.alias_or_name.lower()] = derived_columns.get(
                table_name, set()
            )
            continue
        if table_name.startswith(INTERNAL_TABLE_PREFIXES):
            return _blocked("internal_table", "SQLite internal tables are not accessible.")
        if table_node.db or table_node.catalog:
            return _blocked("qualified_database", "Cross-database references are not allowed.")
        if table_name not in referenced_tables:
            referenced_tables.append(table_name)
        table_aliases[table_node.alias_or_name.lower()] = table_name
        table_aliases[table_name] = table_name
    for subquery in expression.find_all(exp.Subquery):
        alias = subquery.alias_or_name.lower()
        if alias:
            table_aliases[alias] = "__derived__"
            if isinstance(subquery.this, exp.Select):
                derived_columns[alias] = {
                    projection.alias_or_name.lower()
                    for projection in subquery.this.expressions
                    if projection.alias_or_name
                }

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
        if qualifier:
            table_name = table_aliases.get(qualifier)
            if table_name in {"__cte__", "__derived__"}:
                if name not in derived_columns.get(qualifier, set()):
                    return SqlValidationResult(
                        safe=False,
                        repairable=True,
                        normalized_sql=expression.sql(dialect="sqlite"),
                        reason_code="unknown_column",
                        reason="The SQL references an unknown derived column.",
                        referenced_tables=referenced_tables,
                        referenced_columns=referenced_columns,
                    )
                continue
            if table_name is None or name not in catalog.get(table_name, set()):
                return SqlValidationResult(
                    safe=False,
                    repairable=True,
                    normalized_sql=expression.sql(dialect="sqlite"),
                    reason_code="unknown_column",
                    reason="The SQL references an unknown column.",
                    referenced_tables=referenced_tables,
                    referenced_columns=referenced_columns,
                )
            qualified = f"{table_name}.{name}"
        else:
            matching = [table for table in referenced_tables if name in catalog.get(table, set())]
            if not matching and name not in select_aliases:
                return SqlValidationResult(
                    safe=False,
                    repairable=True,
                    normalized_sql=expression.sql(dialect="sqlite"),
                    reason_code="unknown_column",
                    reason="The SQL references an unknown column.",
                    referenced_tables=referenced_tables,
                    referenced_columns=referenced_columns,
                )
            qualified = f"{matching[0]}.{name}" if len(matching) == 1 else name
        if qualified not in referenced_columns:
            referenced_columns.append(qualified)

    if (
        _has_nonunique_derived_self_join(expression, schema=schema)
        or _has_flat_sibling_aggregate_fanout(
            expression,
            schema=schema,
            table_aliases=table_aliases,
            referenced_tables=referenced_tables,
        )
        or _has_repeated_joined_measure(
            expression,
            schema=schema,
        )
    ):
        return SqlValidationResult(
            safe=False,
            repairable=True,
            normalized_sql=expression.sql(dialect="sqlite"),
            reason_code="aggregate_fanout",
            reason=(
                "Aggregates from sibling one-to-many tables must be computed at the parent "
                "grain before joining."
            ),
            referenced_tables=referenced_tables,
            referenced_columns=referenced_columns,
        )

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
