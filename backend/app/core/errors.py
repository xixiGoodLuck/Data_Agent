from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        error_type: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        self.details = details or {}


ERROR_MESSAGES = {
    "dataset_not_found": "The selected dataset does not exist.",
    "invalid_upload": "The CSV upload is invalid.",
    "prompt_blocked": "The request conflicts with the data access policy.",
    "needs_clarification": "More detail is required before this question can be analyzed.",
    "llm_auth_error": "The configured model provider rejected authentication.",
    "llm_balance_error": "The model provider account has insufficient balance.",
    "llm_rate_limit": "The model provider rate limit was reached.",
    "llm_timeout": "The model provider timed out.",
    "llm_network_error": "The model provider is unavailable.",
    "llm_request_error": "The model provider rejected the request format.",
    "llm_provider_error": "The model provider returned a service error.",
    "llm_invalid_output": "The model response could not be validated.",
    "local_model_error": "The local model could not complete the request.",
    "sql_parse_error": "The generated SQL could not be parsed safely.",
    "sql_safety_block": "The generated SQL did not pass the safety gate.",
    "approval_required": "This query requires explicit approval.",
    "approval_rejected": "The sensitive query was rejected.",
    "query_timeout": "The query exceeded the execution time limit.",
    "query_execution_error": "The query could not be executed.",
    "internal_error": "An unexpected internal error occurred.",
}
