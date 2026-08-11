from __future__ import annotations

from typing import Any, Literal

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp


class RiskAssessment(BaseModel):
    level: Literal["low", "medium", "high"] = "low"
    reasons: list[str] = Field(default_factory=list)
    requires_approval: bool = False


def assess_query_risk(
    normalized_sql: str,
    *,
    schema: dict[str, Any],
    referenced_columns: list[str],
) -> RiskAssessment:
    expression = sqlglot.parse_one(normalized_sql, read="sqlite")
    sensitive = {
        f"{table.lower()}.{column['name'].lower()}"
        for table, details in schema.items()
        for column in details.get("columns", [])
        if column.get("sensitive")
    }
    referenced_sensitive = sensitive.intersection({column.lower() for column in referenced_columns})
    selected_sensitive: set[str] = set()
    final_projections = list(expression.selects)
    for projection in final_projections:
        for column in projection.find_all(exp.Column):
            name = column.name.lower()
            candidates = (
                {f"{column.table.lower()}.{name}"}
                if column.table
                else {item for item in sensitive if item.endswith(f".{name}")}
            )
            if not candidates.intersection(sensitive):
                continue
            if column.find_ancestor(exp.AggFunc) is None:
                selected_sensitive.update(candidates.intersection(sensitive))

    ctes = {cte.alias_or_name.lower(): cte.this for cte in expression.find_all(exp.CTE)}

    def aggregate_relation(query: exp.Expression, seen: set[str] | None = None) -> bool:
        if any(isinstance(node, exp.AggFunc) for node in query.walk()):
            return True
        seen = set(seen or ())
        source_names = {
            table.name.lower() for table in query.find_all(exp.Table) if table.name.lower() in ctes
        }
        if not source_names:
            return False
        for name in source_names:
            if name in seen or not aggregate_relation(ctes[name], seen | {name}):
                return False
        return True

    final_source_names = {
        table.name.lower()
        for table in expression.find_all(exp.Table)
        if table.find_ancestor(exp.Select) is expression
    }
    projects_star = any(
        isinstance(projection, exp.Star)
        or (isinstance(projection, exp.Column) and projection.is_star)
        for projection in final_projections
    )
    projects_raw_star = projects_star and (
        not final_source_names
        or any(
            name not in ctes or not aggregate_relation(ctes[name]) for name in final_source_names
        )
    )

    has_aggregate = any(isinstance(node, exp.AggFunc) for node in expression.walk())
    if referenced_sensitive and not has_aggregate:
        selected_sensitive.update(referenced_sensitive)

    reasons: list[str] = []
    level: Literal["low", "medium", "high"] = "low"
    if projects_raw_star:
        level = "medium"
        reasons.append("Query uses SELECT * and may return broad row-level data")
    if selected_sensitive:
        level = "medium"
        labels = ", ".join(sorted(selected_sensitive))
        reasons.append(f"Query returns sensitive row-level columns: {labels}")
    if any(item.endswith(".email") for item in selected_sensitive):
        level = "high"
        reasons.append("Raw email addresses are highly sensitive identifiers")
    if len(selected_sensitive) >= 2:
        level = "high"
        reasons.append("Query combines multiple sensitive identifiers")

    limit = expression.args.get("limit")
    requested_limit = 100
    if limit is not None and limit.expression is not None:
        try:
            requested_limit = int(limit.expression.name)
        except (TypeError, ValueError):
            requested_limit = 100
    if not has_aggregate and requested_limit >= 50 and len(referenced_columns) >= 4:
        if level == "low":
            level = "medium"
        reasons.append("Query requests a broad non-aggregated row-level result")

    return RiskAssessment(level=level, reasons=reasons, requires_approval=level != "low")
