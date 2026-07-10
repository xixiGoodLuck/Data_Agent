from fastapi import Request

from app.agent.service import QueryService
from app.core.config import Settings
from app.core.db import MetadataDatabase


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_metadata(request: Request) -> MetadataDatabase:
    return request.app.state.metadata


def get_query_service(request: Request) -> QueryService:
    return request.app.state.query_service
