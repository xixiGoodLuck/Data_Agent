from __future__ import annotations

import math
from statistics import mean
from typing import Any


def rate(values: list[bool]) -> float:
    return round(100.0 * sum(values) / len(values), 2) if values else 100.0


def average(values: list[float]) -> float:
    return round(mean(values), 3) if values else 0.0


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return round(ordered[index], 3)


def assertion_passed(assertion: dict[str, Any] | None, response: dict[str, Any]) -> bool:
    if not assertion:
        return True
    kind = assertion.get("type")
    row_count = int(response.get("row_count", 0))
    rows = response.get("rows") or []
    if kind == "row_count_between":
        return int(assertion.get("min", 0)) <= row_count <= int(assertion.get("max", 100))
    if kind == "non_empty":
        return row_count > 0
    if kind == "empty":
        return row_count == 0
    if kind == "scalar_positive":
        if row_count != 1 or not rows:
            return False
        return any(isinstance(value, (int, float)) and value > 0 for value in rows[0].values())
    return False
