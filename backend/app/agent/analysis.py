from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.agent.language import is_chinese
from app.agent.state import DataAnalysisState
from app.schemas.query import Evidence


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
    for column in numeric_columns:
        values = [_number(row.get(column)) for row in rows]
        numbers = [value for value in values if value is not None]
        if not numbers:
            continue
        name = _key(column)
        key_values[f"{name}_min"] = min(numbers)
        key_values[f"{name}_max"] = max(numbers)

    if len(rows) >= 2:
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
    elif rows:
        limitations.append(
            "仅有一行结果, 无法计算期间变化。"
            if zh
            else "Only one result row was available, so period change could not be calculated."
        )
    else:
        limitations.append(
            "经过校验的查询没有返回数据。" if zh else "The validated query returned no rows."
        )

    if rows:
        first = rows[0]
        for column in columns:
            if column in sensitive or column in numeric_columns:
                continue
            value = first.get(column)
            if isinstance(value, str | int | float | bool) and len(str(value)) <= 120:
                key_values[f"top_{_key(column)}"] = value
                break

    if state.get("row_count", 0) > len(rows):
        limitations.append(
            "证据摘要基于受限的返回行计算。"
            if zh
            else "The evidence summary was computed from the bounded result rows."
        )

    return Evidence(
        id=str(uuid5(NAMESPACE_URL, f"insightops:{state['request_id']}:{step_id}:evidence")),
        step_id=step_id,
        question=state["active_analysis_question"],
        sql=state["normalized_sql"],
        result_summary=" ".join(summary_parts)[:2_000],
        key_values=key_values,
        row_count=state.get("row_count", 0),
        lineage=state.get("lineage"),
        limitations=limitations,
        created_at=datetime.now(UTC),
    )
