from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StatsOverview(BaseModel):
    total_queries: int
    success_count: int
    success_rate: float
    blocked_count: int
    pending_approval_count: int
    failed_count: int
    fallback_rate: float
    average_latency_ms: float
    p95_latency_ms: float
    chart_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    top_datasets: list[dict[str, Any]] = Field(default_factory=list)
    recent_queries: list[dict[str, Any]] = Field(default_factory=list)
    recent_failures: list[dict[str, Any]] = Field(default_factory=list)
