from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChartConfig(BaseModel):
    type: Literal["bar", "line", "area", "pie", "scatter", "table", "number"]
    x_column: str | None = None
    y_columns: list[str] = Field(default_factory=list)
    series_name: str | None = None
    title: str
    value_format: Literal["number", "currency", "percent"] = "number"


def _is_numeric(values: list[Any]) -> bool:
    non_null = [value for value in values if value is not None]
    return bool(non_null) and all(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in non_null
    )


def plan_chart(question: str, columns: list[str], rows: list[dict[str, Any]]) -> ChartConfig:
    if not columns or not rows:
        return ChartConfig(type="table", title="Query result")
    numeric = [column for column in columns if _is_numeric([row.get(column) for row in rows])]
    categories = [column for column in columns if column not in numeric]
    lowered = question.lower()
    currency_terms = ("revenue", "mrr", "salary", "price", "refund", "sales", "amount")
    percent_terms = ("rate", "percent", "percentage", "share")
    value_format: Literal["number", "currency", "percent"] = "number"
    if any(term in " ".join(numeric).lower() or term in lowered for term in currency_terms):
        value_format = "currency"
    if any(term in lowered for term in percent_terms):
        value_format = "percent"

    if len(rows) == 1 and len(numeric) == 1:
        return ChartConfig(
            type="number",
            y_columns=numeric,
            series_name=numeric[0].replace("_", " ").title(),
            title=numeric[0].replace("_", " ").title(),
            value_format=value_format,
        )

    temporal = next(
        (
            column
            for column in categories
            if any(token in column.lower() for token in ("date", "month", "year", "week", "day"))
        ),
        None,
    )
    if temporal and numeric:
        chart_type: Literal["line", "area"] = (
            "area"
            if any(term in lowered for term in ("cumulative", "volume", "new subscriptions"))
            else "line"
        )
        return ChartConfig(
            type=chart_type,
            x_column=temporal,
            y_columns=numeric[:3],
            title="Trend over time",
            value_format=value_format,
        )

    if len(numeric) >= 2 and any(
        term in lowered for term in ("relationship", "correlation", "scatter")
    ):
        return ChartConfig(
            type="scatter",
            x_column=numeric[0],
            y_columns=[numeric[1]],
            title="Numeric relationship",
            value_format=value_format,
        )

    if categories and numeric:
        category = categories[0]
        if len(rows) <= 8 and any(
            term in lowered for term in ("breakdown", "distribution", "share", "proportion")
        ):
            return ChartConfig(
                type="pie",
                x_column=category,
                y_columns=[numeric[0]],
                title="Distribution",
                value_format=value_format,
            )
        return ChartConfig(
            type="bar",
            x_column=category,
            y_columns=numeric[:3],
            title="Comparison",
            value_format=value_format,
        )

    return ChartConfig(type="table", title="Query result")
