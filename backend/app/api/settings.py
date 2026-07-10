from fastapi import APIRouter, Depends

from app.api.dependencies import get_settings
from app.core.config import Settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/public")
def public_settings(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "provider": settings.llm_provider,
        "mode": "mock" if settings.llm_provider == "mock" else "real",
        "model": settings.openai_model if settings.llm_provider != "mock" else "deterministic-mock",
        "upload_limits": {
            "max_bytes": settings.max_upload_bytes,
            "max_rows": settings.max_upload_rows,
            "max_columns": settings.max_upload_columns,
        },
        "max_result_rows": settings.max_result_rows,
        "query_timeout_seconds": settings.query_timeout_seconds,
    }
