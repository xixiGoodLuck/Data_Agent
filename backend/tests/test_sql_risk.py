from __future__ import annotations

from app.sql.risk import assess_query_risk

SCHEMA = {
    "employees": {
        "columns": [
            {"name": "department", "type": "TEXT", "sensitive": False},
            {"name": "salary", "type": "REAL", "sensitive": True},
            {"name": "employee_name", "type": "TEXT", "sensitive": True},
        ]
    }
}


def assess(sql: str, referenced: list[str]):
    return assess_query_risk(sql, schema=SCHEMA, referenced_columns=referenced)


def test_star_from_base_table_still_requires_approval() -> None:
    result = assess(
        "SELECT * FROM employees LIMIT 100",
        ["employees.department", "employees.salary", "employees.employee_name"],
    )

    assert result.requires_approval is True
    assert "SELECT *" in result.reasons[0]


def test_star_from_aggregated_cte_is_not_treated_as_row_level() -> None:
    result = assess(
        "WITH department_salary AS ("
        "SELECT department, AVG(salary) AS avg_salary FROM employees GROUP BY department"
        ") SELECT * FROM department_salary",
        ["employees.department", "employees.salary"],
    )

    assert result.requires_approval is False


def test_sensitive_input_to_final_aggregate_is_not_a_row_level_projection() -> None:
    result = assess(
        "WITH base AS (SELECT department, salary FROM employees) "
        "SELECT department, AVG(salary) AS avg_salary FROM base GROUP BY department",
        ["employees.department", "employees.salary"],
    )

    assert result.requires_approval is False


def test_sensitive_final_projection_still_requires_approval() -> None:
    result = assess(
        "SELECT employee_name, salary FROM employees LIMIT 100",
        ["employees.employee_name", "employees.salary"],
    )

    assert result.requires_approval is True
    assert any("sensitive row-level" in reason for reason in result.reasons)
