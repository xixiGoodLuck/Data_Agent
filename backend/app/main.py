from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.checkpoint import CheckpointManager
from app.agent.graph import build_analysis_graph
from app.agent.llm import LLMClientResolver, get_llm_client
from app.agent.nodes import AnalysisNodes
from app.agent.service import QueryService
from app.api import approvals, conversations, datasets, evals, health, logs, query, settings, stats
from app.core.config import Settings, get_settings
from app.core.db import MetadataDatabase
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.data.seed import seed_builtin_datasets

logger = logging.getLogger(__name__)


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings_value = settings_override or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings_value.ensure_runtime_dirs()
        configure_logging(settings_value.log_level)
        metadata = MetadataDatabase(settings_value.app_db_path)
        metadata.initialize()
        with metadata.session() as session:
            seed_builtin_datasets(session, settings_value)
        checkpoint = CheckpointManager(settings_value.checkpoint_db_path)
        llm = get_llm_client(settings_value)
        llm_resolver = LLMClientResolver(llm)
        nodes = AnalysisNodes(settings=settings_value, metadata=metadata, llm=llm_resolver)
        graph = build_analysis_graph(nodes, checkpoint.saver)
        query_service = QueryService(
            settings=settings_value,
            metadata=metadata,
            graph=graph,
            llm_resolver=llm_resolver,
        )
        app.state.metadata = metadata
        app.state.checkpoint = checkpoint
        app.state.graph = graph
        app.state.llm_resolver = llm_resolver
        app.state.query_service = query_service
        try:
            yield
        finally:
            checkpoint.close()
            metadata.close()

    app = FastAPI(
        title=settings_value.app_name,
        version=settings_value.version,
        lifespan=lifespan,
    )
    app.state.settings = settings_value
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings_value.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Request-ID",
            "X-DeepSeek-API-Key",
        ],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "type": exc.error_type,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_error",
                    "message": "An unexpected internal error occurred.",
                    "details": {},
                }
            },
        )

    app.include_router(health.router)
    app.include_router(datasets.router)
    app.include_router(conversations.router)
    app.include_router(query.router)
    app.include_router(approvals.router)
    app.include_router(logs.router)
    app.include_router(stats.router)
    app.include_router(evals.router)
    app.include_router(settings.router)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": settings_value.app_name, "docs": "/docs", "health": "/health"}

    return app


app = create_app()
