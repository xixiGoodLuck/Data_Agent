from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.agent.language import is_chinese
from app.agent.state import DataAnalysisState
from app.schemas.query import Evidence, EvidenceFact, ResultShape, ResultShapeMetadata

_TIME_NAME = re.compile(r"(?:^|_)(?:date|time|month|week|quarter|year|period)(?:_|$)")
_NUMERIC_TYPE = re.compile(r"INT|REAL|NUMERIC|DECIMAL|FLOAT|DOUBLE", re.IGNORECASE)
_RANKING_TERMS = (
    "top",
    "bottom",
    "highest",
    "lowest",
    "rank",
    "最大",
    "最小",
    "最高",
    "最低",
    "排名",
)


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:80]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _sensitive_columns(state: DataAnalysisState) -> set[str]:
    return {
        column["name"]
        for details in state.get("dataset_schema", {}).values()
        for column in details.get("columns", [])
        if column.get("sensitive")
    }


def _metric_label(column: str) -> str:
    return {
        "order_count": "订单量",
        "orders": "订单量",
        "average_order_value": "平均订单金额",
        "average_revenue": "平均收入",
        "total_revenue": "收入",
        "revenue": "收入",
        "refund_amount": "退款金额",
        "mrr": "月度经常性收入",
        "headcount": "人数",
        "quantity": "数量",
    }.get(_key(column), column)


def build_dataset_capability(
    schema: dict[str, Any], column_mapping: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build a lightweight, sample-free capability catalog from persisted schema metadata."""

    mapping = {
        str(item.get("sanitized")): str(item.get("original"))[:256]
        for item in (column_mapping or [])
        if isinstance(item, dict) and item.get("sanitized") and item.get("original")
    }
    qualify = len(schema) > 1
    metrics: list[str] = []
    dimensions: list[str] = []
    time_fields: list[str] = []
    source_columns: list[dict[str, str]] = []
    relationships: list[dict[str, str]] = []
    for table, details in schema.items():
        foreign_key_columns = {
            str(foreign_key.get("from_column", ""))
            for foreign_key in details.get("foreign_keys", [])
        }
        for column in details.get("columns", []):
            name = str(column.get("name", ""))
            if not name:
                continue
            rendered = f"{table}.{name}" if qualify else name
            source_columns.append(
                {
                    "table": table,
                    "name": name,
                    "source_name": mapping.get(name, name),
                }
            )
            if _TIME_NAME.search(name.lower()):
                time_fields.append(rendered)
            elif _NUMERIC_TYPE.search(str(column.get("type", ""))):
                if not column.get("primary_key") and name not in foreign_key_columns:
                    metrics.append(rendered)
            elif not column.get("primary_key") and name not in foreign_key_columns:
                dimensions.append(rendered)
        for foreign_key in details.get("foreign_keys", []):
            relationships.append(
                {
                    "from": f"{table}.{foreign_key.get('from_column', '')}",
                    "to": (f"{foreign_key.get('to_table', '')}.{foreign_key.get('to_column', '')}"),
                }
            )
    return {
        "available_tables": list(schema),
        "metrics": metrics,
        "dimensions": dimensions,
        "time_fields": time_fields,
        "relationships": relationships,
        "source_columns": source_columns,
    }


def _schema_time_names(state: DataAnalysisState) -> set[str]:
    return {
        str(column.get("name", "")).lower()
        for details in state.get("dataset_schema", {}).values()
        for column in details.get("columns", [])
        if _TIME_NAME.search(str(column.get("name", "")).lower())
    }


def infer_result_shape(
    state: DataAnalysisState,
    *,
    numeric_columns: list[str] | None = None,
) -> ResultShape:
    rows = state.get("rows", [])
    columns = state.get("columns", [])
    numeric = set(numeric_columns or [])
    dimension_columns = [column for column in columns if column not in numeric]
    lowered_columns = [column.lower() for column in columns]
    time_names = _schema_time_names(state)
    has_time_dimension = any(
        _TIME_NAME.search(column.lower())
        or column.lower() in time_names
        or any(column.lower().endswith(f"_{name}") for name in time_names)
        for column in dimension_columns
    )
    has_period_pair = any(
        column.startswith(("previous_", "prev_", "prior_")) for column in lowered_columns
    ) and any(column.startswith(("current_", "curr_", "latest_")) for column in lowered_columns)
    if len(rows) <= 1:
        return "period_comparison" if has_period_pair else "scalar"
    if has_time_dimension:
        return "time_series"
    question = state.get("active_analysis_question") or state.get("question") or ""
    sql = state.get("normalized_sql") or state.get("generated_sql") or ""
    if dimension_columns and (
        re.search(r"\border\s+by\b", sql, re.IGNORECASE)
        or any(term in question.lower() for term in _RANKING_TERMS)
    ):
        return "ranking"
    return "categorical_breakdown" if dimension_columns else "scalar"


def _bounded_value(value: Any) -> Any | None:
    if isinstance(value, str | int | float | bool) and len(str(value)) <= 120:
        return value
    return None


def _add_period_values(
    key_values: dict[str, Any], rows: list[dict[str, Any]], numeric_columns: list[str]
) -> list[tuple[str, float, float, float]]:
    if not rows:
        return []
    row = rows[0]
    previous: dict[str, float] = {}
    current: dict[str, float] = {}
    for column in numeric_columns:
        value = _number(row.get(column))
        if value is None:
            continue
        name = _key(column)
        if name.startswith("prev_"):
            metric = name.removeprefix("prev_")
            previous[metric.removesuffix("_1")] = value
        elif name.startswith("previous_"):
            previous[name.removeprefix("previous_")] = value
        elif name.startswith("prior_"):
            previous[name.removeprefix("prior_")] = value
        elif name.startswith("curr_"):
            current[name.removeprefix("curr_")] = value
        elif name.startswith("current_"):
            current[name.removeprefix("current_")] = value
        elif name.startswith("latest_"):
            current[name.removeprefix("latest_")] = value
        key_values[name] = value
    comparisons: list[tuple[str, float, float, float]] = []
    for metric in sorted(previous.keys() & current.keys()):
        previous_value = previous[metric]
        current_value = current[metric]
        key_values[f"previous_{metric}"] = previous_value
        key_values[f"current_{metric}"] = current_value
        if previous_value:
            change = round((current_value - previous_value) / abs(previous_value) * 100, 4)
            key_values.setdefault(f"{metric}_change_pct", change)
            comparisons.append((metric, previous_value, current_value, change))
    return comparisons


def _shape_metadata(
    state: DataAnalysisState,
    result_shape: ResultShape,
    numeric_columns: list[str],
) -> ResultShapeMetadata:
    columns = state.get("columns", [])
    dimensions = [column for column in columns if column not in numeric_columns]
    schema_time_names = _schema_time_names(state)
    time_column = next(
        (
            column
            for column in dimensions
            if _TIME_NAME.search(column.lower())
            or column.lower() in schema_time_names
            or any(column.lower().endswith(f"_{name}") for name in schema_time_names)
        ),
        None,
    )
    return ResultShapeMetadata(
        shape=result_shape,
        time_column=time_column,
        dimension_columns=dimensions,
        metric_columns=numeric_columns,
        series_columns=[column for column in dimensions if column != time_column],
    )


def _add_time_series_changes(
    *,
    rows: list[dict[str, Any]],
    metadata: ResultShapeMetadata,
    key_values: dict[str, Any],
    summary_parts: list[str],
    zh: bool,
) -> dict[str, dict[str, float]]:
    if not metadata.time_column:
        return {}
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        series_key = tuple(str(row.get(column, "")) for column in metadata.series_columns)
        groups.setdefault(series_key, []).append(row)

    series_changes: dict[str, dict[str, float]] = {}
    for series_key, series_rows in groups.items():
        ordered = sorted(series_rows, key=lambda row: str(row.get(metadata.time_column, "")))
        if len(ordered) < 2:
            continue
        previous, current = ordered[-2:]
        label = " | ".join(series_key) if series_key else "__single__"
        changes: dict[str, float] = {}
        for column in metadata.metric_columns:
            previous_value = _number(previous.get(column))
            current_value = _number(current.get(column))
            if previous_value is None or current_value is None or previous_value == 0:
                continue
            metric = _key(column)
            change_pct = round((current_value - previous_value) / abs(previous_value) * 100, 4)
            changes[f"previous_{metric}"] = previous_value
            changes[f"current_{metric}"] = current_value
            changes[f"{metric}_change_pct"] = change_pct
        if changes:
            series_changes[label] = changes

    if not metadata.series_columns and "__single__" in series_changes:
        changes = series_changes["__single__"]
        key_values.update(changes)
        for column in metadata.metric_columns[:5]:
            metric = _key(column)
            previous_value = changes.get(f"previous_{metric}")
            current_value = changes.get(f"current_{metric}")
            change_pct = changes.get(f"{metric}_change_pct")
            if previous_value is None or current_value is None or change_pct is None:
                continue
            summary_parts.append(
                f"{_metric_label(column)} changed {change_pct:+.2f}%."
                if zh
                else f"{column} changed from {previous_value:g} to {current_value:g} ({change_pct:+.2f}%)."
            )
    return series_changes


def _build_facts(
    evidence_id: str,
    key_values: dict[str, Any],
    series_changes: dict[str, dict[str, float]],
) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    for key, value in key_values.items():
        bounded = _bounded_value(value)
        if bounded is None:
            continue
        facts.append(
            EvidenceFact(
                fact_id=f"{_key(evidence_id)[:12]}.{key}",
                metric=key,
                statistic=key,
                value=bounded,
                unit="percent" if key.endswith("_pct") else None,
            )
        )
    for series, changes in series_changes.items():
        for key, value in changes.items():
            facts.append(
                EvidenceFact(
                    fact_id=f"{_key(evidence_id)[:12]}.{_key(series)}.{key}",
                    metric=(
                        key.removeprefix("previous_")
                        .removeprefix("current_")
                        .removesuffix("_change_pct")
                    ),
                    dimension="series",
                    dimension_value=series,
                    statistic=(
                        "change_pct"
                        if key.endswith("_change_pct")
                        else "previous"
                        if key.startswith("previous_")
                        else "current"
                    ),
                    value=value,
                    unit="percent" if key.endswith("_change_pct") else None,
                )
            )
    return facts[:200]


def build_evidence(state: DataAnalysisState) -> Evidence:
    step_id = state["current_analysis_step_id"]
    rows = state.get("rows", [])
    columns = state.get("columns", [])
    sensitive = _sensitive_columns(state)
    key_values: dict[str, Any] = {}
    limitations: list[str] = []
    zh = is_chinese(state.get("response_language", "en"))
    summary_parts = [
        f"返回 {state.get('row_count', 0)} 行。"
        if zh
        else f"{state.get('row_count', 0)} row(s) returned."
    ]

    numeric_columns = [
        column
        for column in columns
        if column not in sensitive and any(_number(row.get(column)) is not None for row in rows)
    ][:8]
    result_shape = infer_result_shape(state, numeric_columns=numeric_columns)
    metadata = _shape_metadata(state, result_shape, numeric_columns)
    for column in numeric_columns:
        values = [_number(row.get(column)) for row in rows]
        numbers = [value for value in values if value is not None]
        if not numbers:
            continue
        name = _key(column)
        key_values[f"{name}_min"] = min(numbers)
        key_values[f"{name}_max"] = max(numbers)

    series_changes: dict[str, dict[str, float]] = {}
    if result_shape == "time_series" and len(rows) >= 2 and metadata.time_column:
        series_changes = _add_time_series_changes(
            rows=rows,
            metadata=metadata,
            key_values=key_values,
            summary_parts=summary_parts,
            zh=zh,
        )
    elif result_shape == "time_series" and len(rows) >= 2:
        previous = rows[-2]
        current = rows[-1]
        comparisons: list[str] = []
        for column in numeric_columns:
            previous_value = _number(previous.get(column))
            current_value = _number(current.get(column))
            if previous_value is None or current_value is None:
                continue
            name = _key(column)
            key_values[f"previous_{name}"] = previous_value
            key_values[f"current_{name}"] = current_value
            if previous_value != 0:
                change_pct = round((current_value - previous_value) / abs(previous_value) * 100, 4)
                key_values[f"{name}_change_pct"] = change_pct
                comparisons.append(
                    f"{_metric_label(column)}从 {previous_value:g} 变化到 {current_value:g}, "
                    f"变化 {change_pct:+.2f}%。"
                    if zh
                    else f"{column} changed from {previous_value:g} to {current_value:g} "
                    f"({change_pct:+.2f}%)."
                )
        summary_parts.extend(comparisons[:5])
    elif result_shape == "period_comparison":
        for column, previous_value, current_value, change_pct in _add_period_values(
            key_values, rows, numeric_columns
        ):
            summary_parts.append(
                f"{_metric_label(column)}从 {previous_value:g} 变化到 {current_value:g}, "
                f"变化 {change_pct:+.2f}%。"
                if zh
                else f"{column} changed from {previous_value:g} to {current_value:g} "
                f"({change_pct:+.2f}%)."
            )
    elif rows and result_shape == "time_series":
        limitations.append(
            "仅有一行结果, 无法计算期间变化。"
            if zh
            else "Only one result row was available, so period change could not be calculated."
        )
    elif not rows:
        limitations.append(
            "经过校验的查询没有返回数据。" if zh else "The validated query returned no rows."
        )

    if rows:
        first = rows[0]
        last = rows[-1]
        dimension_columns = [
            column
            for column in columns
            if column not in sensitive and column not in numeric_columns
        ]
        for column in dimension_columns[:3]:
            first_value = first.get(column)
            last_value = last.get(column)
            if isinstance(first_value, str | int | float | bool) and len(str(first_value)) <= 120:
                key_values[f"first_{_key(column)}"] = first_value
            if isinstance(last_value, str | int | float | bool) and len(str(last_value)) <= 120:
                key_values[f"last_{_key(column)}"] = last_value
        if dimension_columns and result_shape in {"ranking", "categorical_breakdown"}:
            dimension = dimension_columns[0]
            metric = numeric_columns[0] if numeric_columns else None
            ranked_rows = rows
            if result_shape == "categorical_breakdown" and metric:
                ranked_rows = sorted(
                    (row for row in rows if _number(row.get(metric)) is not None),
                    key=lambda row: _number(row.get(metric)) or 0,
                    reverse=True,
                )
            if ranked_rows:
                top = ranked_rows[0]
                bottom = ranked_rows[-1]
                top_dimension = _bounded_value(top.get(dimension))
                bottom_dimension = _bounded_value(bottom.get(dimension))
                if top_dimension is not None:
                    key_values["top_dimension"] = top_dimension
                    key_values[f"top_{_key(dimension)}"] = top_dimension
                if bottom_dimension is not None:
                    key_values["bottom_dimension"] = bottom_dimension
                    key_values[f"bottom_{_key(dimension)}"] = bottom_dimension
                if metric:
                    top_metric = _number(top.get(metric))
                    bottom_metric = _number(bottom.get(metric))
                    if top_metric is not None:
                        key_values["top_metric"] = top_metric
                    if bottom_metric is not None:
                        key_values["bottom_metric"] = bottom_metric
            key_values["row_count"] = len(rows)

    if state.get("is_truncated", False):
        limitations.append(
            f"结果已截断, 仅基于前 {state.get('returned_row_count', len(rows))} 行。"
            if zh
            else (
                "The result was truncated and the evidence is based only on the first "
                f"{state.get('returned_row_count', len(rows))} rows."
            )
        )

    evidence_id = str(uuid5(NAMESPACE_URL, f"insightops:{state['request_id']}:{step_id}:evidence"))
    return Evidence(
        id=evidence_id,
        step_id=step_id,
        question=state["active_analysis_question"],
        sql=state["normalized_sql"],
        result_shape=result_shape,
        result_shape_metadata=metadata,
        result_summary=" ".join(summary_parts)[:2_000],
        key_values=key_values,
        series_changes=series_changes,
        facts=_build_facts(evidence_id, key_values, series_changes),
        row_count=state.get("row_count", 0),
        returned_row_count=state.get("returned_row_count", len(rows)),
        is_truncated=state.get("is_truncated", False),
        lineage=state.get("lineage"),
        limitations=limitations,
        created_at=datetime.now(UTC),
    )
