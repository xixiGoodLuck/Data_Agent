from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from app.api.dependencies import get_metadata, get_settings
from app.core.config import Settings
from app.core.db import MetadataDatabase

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/api/health")
def health(
    request: Request,
    metadata: MetadataDatabase = Depends(get_metadata),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    app_database = "ok"
    checkpoint = "ok"
    dataset_storage = "ok"
    try:
        with metadata.session() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        app_database = "error"
    try:
        request.app.state.checkpoint.connection.execute("SELECT 1").fetchone()
    except Exception:
        checkpoint = "error"
    if not settings.datasets_dir.exists() or not settings.datasets_dir.is_dir():
        dataset_storage = "error"
    status = "ok" if {app_database, checkpoint, dataset_storage} == {"ok"} else "degraded"
    return {
        "status": status,
        "app_database": app_database,
        "checkpoint": checkpoint,
        "dataset_storage": dataset_storage,
        "llm_provider": settings.llm_provider,
        "version": settings.version,
    }
