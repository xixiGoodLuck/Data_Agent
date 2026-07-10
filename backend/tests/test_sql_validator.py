from __future__ import annotations

import pytest

from app.sql.validator import validate_sql

SCHEMA = {
    "sales": {
        "columns": [
            {"name": "id", "type": "INTEGER"},
            {"name": "order_date", "type": "TEXT"},
            {"name": "region", "type": "TEXT"},
            {"name": "revenue", "type": "REAL"},
        ]
    },
    "customers": {
        "columns": [
            {"name": "id", "type": "INTEGER"},
            {"name": "city", "type": "TEXT"},
        ]
    },
    "orders": {
        "columns": [
            {"name": "id", "type": "INTEGER"},
            {"name": "customer_id", "type": "INTEGER"},
            {"name": "status", "type": "TEXT"},
        ]
    },
}


def validate(sql: str, tables: list[str] | None = None):
    allowed = tables or ["sales"]
    return validate_sql(
        sql,
        allowed_tables=allowed,
        schema={table: SCHEMA[table] for table in allowed if table in SCHEMA},
    )


def test_safe_select_appends_limit() -> None:
    result = validate("SELECT region, SUM(revenue) AS total FROM sales GROUP BY region")
    assert result.safe is True
    assert result.normalized_sql.endswith("LIMIT 100")
    assert result.referenced_tables == ["sales"]
    assert {"sales.region", "sales.revenue"}.issubset(result.referenced_columns)


def test_cte_select_is_allowed() -> None:
    result = validate(
        "WITH totals AS (SELECT region, SUM(revenue) AS total FROM sales GROUP BY region) "
        "SELECT region, total FROM totals ORDER BY total DESC"
    )
    assert result.safe is True
    assert result.referenced_tables == ["sales"]


def test_safe_join_is_allowed() -> None:
    result = validate(
        "SELECT c.city, COUNT(o.id) AS orders FROM customers c "
        "JOIN orders o ON o.customer_id = c.id GROUP BY c.city",
        ["customers", "orders"],
    )
    assert result.safe is True
    assert set(result.referenced_tables) == {"customers", "orders"}


def test_one_trailing_semicolon_is_normalized() -> None:
    result = validate("SELECT region FROM sales;")
    assert result.safe is True
    assert ";" not in result.normalized_sql


def test_smaller_limit_is_preserved() -> None:
    assert validate("SELECT region FROM sales LIMIT 5").normalized_sql.endswith("LIMIT 5")


def test_large_limit_is_clamped() -> None:
    assert validate("SELECT region FROM sales LIMIT 10000").normalized_sql.endswith("LIMIT 100")


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("DROP TABLE sales", "write_operation"),
        ("UPDATE sales SET revenue = 0", "write_operation"),
        ("DELETE FROM sales", "write_operation"),
        ("INSERT INTO sales (id) VALUES (1)", "write_operation"),
        ("ATTACH DATABASE 'other.db' AS other", "write_operation"),
        ("PRAGMA database_list", "write_operation"),
        ("VACUUM", "write_operation"),
        ("SELECT load_extension('x') FROM sales", "forbidden_function"),
    ],
)
def test_dangerous_statements_are_blocked(sql: str, reason: str) -> None:
    result = validate(sql)
    assert result.safe is False
    assert result.reason_code == reason


def test_multiple_statements_are_blocked() -> None:
    result = validate("SELECT region FROM sales; DROP TABLE sales")
    assert result.safe is False
    assert result.reason_code == "multiple_statements"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT region FROM sales -- hidden statement",
        "SELECT region FROM sales /* hidden */",
    ],
)
def test_comment_attacks_are_blocked(sql: str) -> None:
    assert validate(sql).reason_code == "comments_forbidden"


def test_unknown_table_is_blocked() -> None:
    assert validate("SELECT * FROM secrets").reason_code == "unknown_table"


def test_cross_dataset_table_is_blocked() -> None:
    result = validate_sql(
        "SELECT sales.region FROM sales JOIN orders ON orders.id = sales.id",
        allowed_tables=["sales"],
        schema={"sales": SCHEMA["sales"]},
    )
    assert result.reason_code == "unknown_table"


def test_sqlite_internal_table_is_blocked() -> None:
    assert validate("SELECT name FROM sqlite_master").reason_code == "internal_table"


def test_unknown_column_is_blocked() -> None:
    assert validate("SELECT imaginary FROM sales").reason_code == "unknown_column"


def test_database_qualified_table_is_blocked() -> None:
    assert validate("SELECT region FROM main.sales").reason_code == "qualified_database"


def test_semicolon_inside_a_string_is_not_a_second_statement() -> None:
    result = validate("SELECT region FROM sales WHERE region = 'North;West'")
    assert result.safe is True
