REPAIRABLE_ERROR_TYPES = {
    "unknown_column",
    "unsupported_function",
    "derived_scope_error",
    "aggregate_fanout",
    "query_too_complex",
    "sqlite_execution_error",
}


def may_repair(error_type: str | None, repairable: bool, attempts: int) -> bool:
    return bool(repairable and error_type in REPAIRABLE_ERROR_TYPES and attempts < 2)
