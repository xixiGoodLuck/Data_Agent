from __future__ import annotations

import re
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


def _has_scoped_sibling_aggregate_fanout(
    expression: exp.Expression, *, schema: dict[str, Any]
) -> bool:
    parents_by_child = {
        table.lower(): {
            foreign_key.get("to_table", "").lower()
            for foreign_key in details.get("foreign_keys", [])
            if foreign_key.get("to_table")
        }
        for table, details in schema.items()
    }
    for scope in traverse_scope(expression):
        source_tables = {
            alias.lower(): source.name.lower()
            for alias, (_, source) in scope.selected_sources.items()
            if isinstance(source, exp.Table)
        }
        aggregate_sources: list[set[str]] = []
        for aggregate in scope.expression.find_all(exp.AggFunc):
            if aggregate.find_ancestor(exp.Select) is not scope.expression:
                continue
            if isinstance(aggregate, exp.Count) and aggregate.find(exp.Distinct) is not None:
                continue
            tables = {
                source_tables[column.table.lower()]
                for column in aggregate.find_all(exp.Column)
                if column.table and column.table.lower() in source_tables
            }
            if tables:
                aggregate_sources.append(tables)
        all_tables = set().union(*aggregate_sources) if aggregate_sources else set()
        for left, right in combinations(sorted(all_tables), 2):
            related = bool(
                parents_by_child.get(left, set()) & parents_by_child.get(right, set())
                or left in parents_by_child.get(right, set())
                or right in parents_by_child.get(left, set())
            )
            combined_safely = any({left, right}.issubset(tables) for tables in aggregate_sources)
            if related and not combined_safely:
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
        projected_names = {
            projection.alias_or_name.lower()
            for projection in source.expression.selects
            if projection.alias_or_name
        }
        if source.expression.args.get("distinct") and projected_names.issubset(columns):
            return True
        group = source.expression.args.get("group")
        group_keys: set[str] = set()
        for item in group.expressions if group else []:
            if item.alias_or_name:
                group_keys.add(item.alias_or_name.lower())
            item_sql = item.sql(dialect="sqlite")
            for projection in source.expression.selects:
                projected = projection.this if isinstance(projection, exp.Alias) else projection
                if projected.sql(dialect="sqlite") == item_sql and projection.alias_or_name:
                    group_keys.add(projection.alias_or_name.lower())
        if bool(group_keys) and group_keys.issubset(columns):
            return True
        if source.expression.args.get("limit") is not None:
            return True
        if group is None and any(
            aggregate.find_ancestor(exp.Select) is source.expression
            for aggregate in source.expression.find_all(exp.AggFunc)
        ):
            return True
        for projection in source.expression.selects:
            if projection.alias_or_name.lower() not in columns:
                continue
            projected = projection.this if isinstance(projection, exp.Alias) else projection
            if not isinstance(projected, exp.Column) or not projected.table:
                continue
            selected = source.selected_sources.get(projected.table.lower())
            selected_source = selected[1] if selected else None
            if not isinstance(selected_source, exp.Table):
                continue
            primary_keys = {
                column["name"].lower()
                for column in schema.get(selected_source.name.lower(), {}).get("columns", [])
                if column.get("primary_key")
            }
            if projected.name.lower() in primary_keys:
                return True
        return False
    primary_keys = {
        column["name"].lower()
        for column in schema.get(source.name.lower(), {}).get("columns", [])
        if column.get("primary_key")
    }
    referenced_keys = {
        foreign_key.get("to_column", "").lower()
        for details in schema.values()
        for foreign_key in details.get("foreign_keys", [])
        if foreign_key.get("to_table", "").lower() == source.name.lower()
        and foreign_key.get("to_column")
    }
    primary_keys.update(referenced_keys)
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
        joined_aliases = {alias for alias, columns in join_columns.items() if columns}
        if len(joined_aliases) >= 2 and not any(unique[alias] for alias in joined_aliases):
            return True
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
    question: str | None = None,
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
        try:
            candidate_statements = sqlglot.parse(cleaned, read="sqlite")
        except sqlglot.errors.ParseError:
            candidate_statements = []
        only_read_queries = len(candidate_statements) > 1 and all(
            isinstance(statement, (exp.Select, exp.SetOperation))
            for statement in candidate_statements
        )
        return SqlValidationResult(
            safe=False,
            repairable=only_read_queries,
            reason_code="multiple_statements",
            reason="Only one SQL statement is allowed.",
        )

    try:
        parsed_statements = sqlglot.parse(cleaned, read="sqlite")
    except sqlglot.errors.ParseError:
        return _blocked("sql_parse_error", "The SQL could not be parsed in SQLite dialect.")
    if len(parsed_statements) != 1 or parsed_statements[0] is None:
        only_read_queries = len(parsed_statements) > 1 and all(
            isinstance(statement, (exp.Select, exp.SetOperation)) for statement in parsed_statements
        )
        return SqlValidationResult(
            safe=False,
            repairable=only_read_queries,
            reason_code="multiple_statements",
            reason="Only one SQL statement is allowed.",
        )
    expression = parsed_statements[0]
    if (
        question
        and not re.search(r"\d{4}(?:年|\b)", question)
        and re.search(r"'\d{4}-\d{2}(?:-\d{2})?'", cleaned)
    ):
        return SqlValidationResult(
            safe=False,
            repairable=True,
            normalized_sql=expression.sql(dialect="sqlite"),
            reason_code="invented_date_literal",
            reason=(
                "The SQL invented a calendar date that was not supplied by the analytical "
                "question; relative periods must be derived from the maximum stored date."
            ),
        )
    nodes = list(expression.walk())
    if len(nodes) > max_ast_nodes:
        return SqlValidationResult(
            safe=False,
            repairable=True,
            normalized_sql=expression.sql(dialect="sqlite"),
            reason_code="query_too_complex",
            reason=(
                "The SQL exceeds the allowed complexity and must be simplified while preserving "
                "the analytical question."
            ),
        )
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
            continue
        if table_name.startswith(INTERNAL_TABLE_PREFIXES):
            return _blocked("internal_table", "SQLite internal tables are not accessible.")
        if table_node.db or table_node.catalog:
            return _blocked("qualified_database", "Cross-database references are not allowed.")
        if table_name not in referenced_tables:
            referenced_tables.append(table_name)
        table_aliases[table_node.alias_or_name.lower()] = table_name

    allowed = {table.lower() for table in allowed_tables}
    if not referenced_tables:
        return _blocked("missing_table", "The SQL does not reference a dataset table.")
    if not set(referenced_tables).issubset(allowed):
        return _blocked("unknown_table", "The SQL references a table outside the selected schema.")

    catalog = _column_catalog(schema)
    referenced_columns: list[str] = []

    def selected_source(scope: Scope, qualifier: str) -> exp.Table | Scope | None:
        current: Scope | None = scope
        while current is not None:
            selected = current.selected_sources.get(qualifier)
            if selected is not None:
                return selected[1]
            current = current.parent
        return None

    def source_columns(source: exp.Table | Scope, seen: set[int] | None = None) -> set[str]:
        if isinstance(source, Scope):
            seen = set(seen or ())
            identity = id(source)
            if identity in seen:
                return set()
            seen.add(identity)
            projected = {
                projection.alias_or_name.lower()
                for projection in source.expression.selects
                if projection.alias_or_name and projection.alias_or_name != "*"
            }
            if any(
                isinstance(projection, exp.Star)
                or (isinstance(projection, exp.Column) and projection.is_star)
                for projection in source.expression.selects
            ):
                for _, nested_source in source.selected_sources.values():
                    projected.update(source_columns(nested_source, seen))
            return projected
        return catalog.get(source.name.lower(), set())

    for scope in traverse_scope(expression):
        select_aliases = {
            projection.alias.lower()
            for projection in scope.expression.selects
            if isinstance(projection, exp.Alias) and projection.alias
        }
        local_sources = [source for _, source in scope.selected_sources.values()]
        for column in scope.columns:
            if column.find_ancestor(exp.Select) is not scope.expression:
                continue
            name = column.name.lower()
            if name == "*":
                continue
            qualifier = column.table.lower() if column.table else ""
            if qualifier:
                source = selected_source(scope, qualifier)
                if isinstance(source, Scope):
                    if name not in source_columns(source):
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
                table_name = source.name.lower() if isinstance(source, exp.Table) else None
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
                matching_sources = [
                    source for source in local_sources if name in source_columns(source)
                ]
                if not matching_sources and name not in select_aliases:
                    return SqlValidationResult(
                        safe=False,
                        repairable=True,
                        normalized_sql=expression.sql(dialect="sqlite"),
                        reason_code="unknown_column",
                        reason="The SQL references an unknown column.",
                        referenced_tables=referenced_tables,
                        referenced_columns=referenced_columns,
                    )
                base_matches = [
                    source.name.lower()
                    for source in matching_sources
                    if isinstance(source, exp.Table)
                ]
                qualified = f"{base_matches[0]}.{name}" if len(base_matches) == 1 else name
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
        or _has_scoped_sibling_aggregate_fanout(expression, schema=schema)
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
