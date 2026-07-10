REPAIRABLE_ERROR_TYPES = {"query_execution_error"}


def may_repair(error_type: str | None, repairable: bool, attempts: int) -> bool:
    return bool(repairable and error_type in REPAIRABLE_ERROR_TYPES and attempts < 1)
