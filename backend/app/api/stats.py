from __future__ import annotations

import math
from collections import Counter
from statistics import mean
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.dependencies import get_metadata
from app.api.logs import _serialize_log
from app.core.db import MetadataDatabase
from app.models import Dataset, QueryLog
from app.schemas.stats import StatsOverview

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _rate(count: int, total: int) -> float:
    return round(100.0 * count / total, 2) if total else 0.0


@router.get("/overview", response_model=StatsOverview)
def overview(metadata: MetadataDatabase = Depends(get_metadata)) -> dict[str, Any]:
    with metadata.session() as session:
        logs = list(
            session.scalars(
                select(QueryLog)
                .where(QueryLog.run_mode == "interactive")
                .order_by(QueryLog.created_at.desc())
            )
        )
        datasets = {dataset.id: dataset.name for dataset in session.scalars(select(Dataset))}
    total = len(logs)
    counts = Counter(log.status for log in logs)
    latencies = sorted(
        log.execution_time_ms
        for log in logs
        if log.completed_at is not None and log.execution_time_ms >= 0
    )
    p95_latency = latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)] if latencies else 0.0
    chart_counts = Counter(log.chart_type for log in logs if log.chart_type)
    dataset_counts = Counter(log.dataset_id for log in logs)
    failures = [log for log in logs if log.status in {"blocked", "failed", "rejected"}]
    return {
        "total_queries": total,
        "success_count": counts["success"],
        "success_rate": _rate(counts["success"], total),
        "blocked_count": counts["blocked"],
        "pending_approval_count": counts["pending_approval"],
        "failed_count": counts["failed"],
        "fallback_rate": _rate(sum(log.used_fallback for log in logs), total),
        "average_latency_ms": round(mean(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": round(p95_latency, 3),
        "chart_breakdown": [
            {"type": chart_type, "count": count} for chart_type, count in chart_counts.most_common()
        ],
        "top_datasets": [
            {"dataset_id": dataset_id, "name": datasets.get(dataset_id), "count": count}
            for dataset_id, count in dataset_counts.most_common(5)
        ],
        "recent_queries": [_serialize_log(log, datasets.get(log.dataset_id)) for log in logs[:8]],
        "recent_failures": [
            _serialize_log(log, datasets.get(log.dataset_id)) for log in failures[:8]
        ],
    }
