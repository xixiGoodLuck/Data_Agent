from __future__ import annotations

from fastapi import Header

from app.core.errors import AppError


def get_temporary_deepseek_key(
    x_deepseek_api_key: str | None = Header(
        default=None,
        alias="X-DeepSeek-API-Key",
        max_length=512,
        include_in_schema=True,
    ),
) -> str | None:
    if x_deepseek_api_key is None:
        return None
    key = x_deepseek_api_key.strip()
    if not key:
        return None
    if any(character.isspace() for character in key):
        raise AppError(
            "llm_auth_error",
            "The temporary DeepSeek API key is malformed.",
            status_code=400,
        )
    return key
