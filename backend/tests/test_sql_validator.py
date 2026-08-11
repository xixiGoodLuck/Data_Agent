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
            {"name": "id", "type": "INTEGER", "primary_key": True},
            {"name": "customer_id", "type": "INTEGER"},
            {"name": "status", "type": "TEXT"},
        ],
        "foreign_keys": [
            {"from_column": "customer_id", "to_table": "customers", "to_column": "id"}
        ],
    },
    "order_items": {
        "columns": [
            {"name": "id", "type": "INTEGER", "primary_key": True},
            {"name": "order_id", "type": "INTEGER"},
            {"name": "line_revenue", "type": "REAL"},
        ],
        "foreign_keys": [{"from_column": "order_id", "to_table": "orders", "to_column": "id"}],
    },
    "refunds": {
        "columns": [
            {"name": "id", "type": "INTEGER"},
            {"name": "order_id", "type": "INTEGER"},
            {"name": "refund_amount", "type": "REAL"},
        ],
        "foreign_keys": [{"from_column": "order_id", "to_table": "orders", "to_column": "id"}],
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


def test_flat_sibling_child_aggregates_require_fanout_safe_repair() -> None:
    result = validate(
        "SELECT SUM(oi.line_revenue), SUM(r.refund_amount) FROM orders o "
        "JOIN order_items oi ON oi.order_id = o.id "
        "LEFT JOIN refunds r ON r.order_id = o.id",
        ["orders", "order_items", "refunds"],
    )

    assert result.safe is False
    assert result.repairable is True
    assert result.reason_code == "aggregate_fanout"


def test_preaggregated_sibling_children_are_fanout_safe() -> None:
    result = validate(
        "WITH item_totals AS ("
        "SELECT order_id, SUM(line_revenue) AS revenue FROM order_items GROUP BY order_id"
        "), refund_totals AS ("
        "SELECT order_id, SUM(refund_amount) AS refunds FROM refunds GROUP BY order_id"
        ") SELECT SUM(i.revenue), SUM(r.refunds) FROM orders o "
        "JOIN item_totals i ON i.order_id = o.id "
        "LEFT JOIN refund_totals r ON r.order_id = o.id",
        ["orders", "order_items", "refunds"],
    )

    assert result.safe is True


def test_allocated_rows_cannot_rejoin_detail_on_a_nonunique_business_key() -> None:
    result = validate(
        "SELECT SUM(oi.line_revenue), SUM(alloc.allocated_refund) "
        "FROM order_items oi LEFT JOIN ("
        "SELECT oi2.order_id, r.refund_amount * oi2.line_revenue AS allocated_refund "
        "FROM order_items oi2 JOIN refunds r ON r.order_id = oi2.order_id"
        ") alloc ON alloc.order_id = oi.order_id",
        ["order_items", "refunds"],
    )

    assert result.safe is False
    assert result.repairable is True
    assert result.reason_code == "aggregate_fanout"


def test_grouped_self_join_is_unique_at_its_join_key() -> None:
    result = validate(
        "SELECT SUM(oi.line_revenue / totals.order_revenue) "
        "FROM order_items oi JOIN ("
        "SELECT order_id, SUM(line_revenue) AS order_revenue "
        "FROM order_items GROUP BY order_id"
        ") totals ON totals.order_id = oi.order_id",
        ["order_items"],
    )

    assert result.safe is True


def test_qualified_columns_from_preaggregated_subquery_are_allowed() -> None:
    result = validate(
        "SELECT SUM(i.revenue), SUM(r.refunds) FROM orders o "
        "JOIN (SELECT order_id, SUM(line_revenue) AS revenue "
        "FROM order_items GROUP BY order_id) i ON i.order_id = o.id "
        "LEFT JOIN (SELECT order_id, SUM(refund_amount) AS refunds "
        "FROM refunds GROUP BY order_id) r ON r.order_id = o.id",
        ["orders", "order_items", "refunds"],
    )

    assert result.safe is True


def test_parent_total_joined_to_child_rows_still_requires_fanout_repair() -> None:
    result = validate(
        "SELECT SUM(oi.line_revenue), SUM(r.refunds) FROM order_items oi "
        "LEFT JOIN (SELECT order_id, SUM(refund_amount) AS refunds "
        "FROM refunds GROUP BY order_id) r ON r.order_id = oi.order_id",
        ["order_items", "refunds"],
    )

    assert result.safe is False
    assert result.repairable is True
    assert result.reason_code == "aggregate_fanout"


def test_explicit_child_share_allocation_is_fanout_safe() -> None:
    result = validate(
        "SELECT SUM(oi.line_revenue), "
        "SUM(r.refunds * oi.line_revenue / totals.order_revenue) AS allocated_refunds "
        "FROM order_items oi "
        "JOIN (SELECT order_id, SUM(line_revenue) AS order_revenue "
        "FROM order_items GROUP BY order_id) totals ON totals.order_id = oi.order_id "
        "LEFT JOIN (SELECT order_id, SUM(refund_amount) AS refunds "
        "FROM refunds GROUP BY order_id) r ON r.order_id = oi.order_id",
        ["order_items", "refunds"],
    )

    assert result.safe is True


def test_distinct_parent_count_with_child_sum_is_fanout_safe() -> None:
    result = validate(
        "SELECT o.status, SUM(oi.line_revenue) / COUNT(DISTINCT o.id) AS average_value "
        "FROM orders o JOIN order_items oi ON oi.order_id = o.id GROUP BY o.status",
        ["orders", "order_items"],
    )

    assert result.safe is True


def test_parent_measure_repeated_across_derived_child_groups_requires_allocation() -> None:
    result = validate(
        "WITH child_groups AS ("
        "SELECT order_id, id AS child_group, SUM(line_revenue) AS revenue "
        "FROM order_items GROUP BY order_id, id"
        "), parent_totals AS ("
        "SELECT order_id, SUM(refund_amount) AS refunds FROM refunds GROUP BY order_id"
        ") SELECT child_group, SUM(parent_totals.refunds) FROM child_groups "
        "LEFT JOIN parent_totals ON parent_totals.order_id = child_groups.order_id "
        "GROUP BY child_group",
        ["order_items", "refunds"],
    )

    assert result.safe is False
    assert result.repairable is True
    assert result.reason_code == "aggregate_fanout"


def test_many_to_many_cte_join_on_incomplete_grain_requires_repair() -> None:
    result = validate(
        "WITH category_orders AS ("
        "SELECT id AS category, order_id, SUM(line_revenue) AS revenue "
        "FROM order_items GROUP BY id, order_id"
        "), allocations AS ("
        "SELECT id AS category, order_id, SUM(line_revenue) AS allocated "
        "FROM order_items GROUP BY id, order_id"
        ") SELECT category, SUM(revenue), SUM(allocated) FROM ("
        "SELECT c.category, c.revenue, a.allocated FROM category_orders c "
        "JOIN allocations a ON a.category = c.category"
        ") joined GROUP BY category",
        ["order_items"],
    )

    assert result.safe is False
    assert result.repairable is True
    assert result.reason_code == "aggregate_fanout"


def test_sibling_aggregates_inside_cte_require_parent_grain_repair() -> None:
    result = validate(
        "WITH product_refunds AS ("
        "SELECT oi.id, SUM(oi.line_revenue) AS revenue, SUM(r.refund_amount) AS refunds "
        "FROM order_items oi LEFT JOIN refunds r ON r.order_id = oi.order_id "
        "GROUP BY oi.id"
        ") SELECT SUM(revenue), SUM(refunds) FROM product_refunds",
        ["order_items", "refunds"],
    )

    assert result.safe is False
    assert result.repairable is True
    assert result.reason_code == "aggregate_fanout"


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
    assert result.repairable is False


def test_multiple_read_queries_are_repairable_but_never_safe() -> None:
    result = validate("SELECT region FROM sales; SELECT product FROM sales")
    assert result.safe is False
    assert result.reason_code == "multiple_statements"
    assert result.repairable is True


def test_cte_aliases_are_validated_in_their_own_query_scope() -> None:
    sql = """
    WITH per_region AS (
        SELECT region AS label, SUM(revenue) AS total_revenue
        FROM sales
        GROUP BY region
    ), overall AS (
        SELECT SUM(revenue) AS total_revenue FROM sales AS o
    )
    SELECT o.total_revenue, r.label, r.total_revenue
    FROM overall AS o
    CROSS JOIN per_region AS r
    """
    result = validate(sql)
    assert result.safe is True


def test_outer_query_can_reference_columns_propagated_through_cte_star() -> None:
    sql = """
    WITH monthly AS (
        SELECT region, SUM(revenue) AS total_revenue
        FROM sales
        GROUP BY region
    ), ranked AS (
        SELECT *, ROW_NUMBER() OVER (ORDER BY total_revenue DESC) AS rn
        FROM monthly
    ), current_m AS (
        SELECT * FROM ranked WHERE rn = 1
    )
    SELECT current_m.region, current_m.total_revenue
    FROM current_m
    """

    result = validate(sql)

    assert result.safe is True


def test_nested_cte_keeps_each_scope_outputs_separate() -> None:
    sql = """
    WITH outer_cte AS (
        WITH inner_cte AS (
            SELECT region AS label, SUM(revenue) AS metric FROM sales GROUP BY region
        )
        SELECT label, metric FROM inner_cte
    )
    SELECT label, metric FROM outer_cte
    """

    assert validate(sql).safe is True


def test_invalid_column_after_cte_star_propagation_is_still_blocked() -> None:
    result = validate(
        "WITH totals AS (SELECT region, SUM(revenue) AS metric FROM sales GROUP BY region), "
        "forwarded AS (SELECT * FROM totals) SELECT missing FROM forwarded"
    )

    assert result.safe is False
    assert result.reason_code == "unknown_column"


def test_join_to_single_row_aggregate_cte_is_not_fanout() -> None:
    sql = """
    WITH plan_counts AS (
        SELECT region, COUNT(*) AS customer_count
        FROM sales GROUP BY region
    ), min_count AS (
        SELECT MIN(customer_count) AS min_customers FROM plan_counts
    )
    SELECT pc.region, pc.customer_count
    FROM plan_counts AS pc
    JOIN min_count AS mc ON pc.customer_count = mc.min_customers
    """

    assert validate(sql).safe is True


def test_join_to_limit_one_cte_is_not_fanout() -> None:
    sql = """
    WITH region_stats AS (
        SELECT region, AVG(revenue) AS avg_revenue FROM sales GROUP BY region
    ), top_region AS (
        SELECT region FROM region_stats ORDER BY avg_revenue DESC LIMIT 1
    )
    SELECT s.order_date, COUNT(*) AS sale_count, AVG(s.revenue) AS avg_revenue
    FROM sales AS s
    JOIN top_region AS t ON s.region = t.region
    GROUP BY s.order_date
    """

    assert validate(sql).safe is True


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
    result = validate("SELECT imaginary FROM sales")

    assert result.safe is False
    assert result.repairable is True
    assert result.reason_code == "unknown_column"
    assert result.normalized_sql == "SELECT imaginary FROM sales"


def test_unknown_cte_output_column_is_repairable() -> None:
    result = validate(
        "WITH totals AS (SELECT region, SUM(revenue) AS revenue FROM sales GROUP BY region) "
        "SELECT totals.missing_value FROM totals"
    )

    assert result.safe is False
    assert result.repairable is True
    assert result.reason_code == "unknown_column"


def test_query_too_complex_is_repairable_without_raising_limit() -> None:
    result = validate_sql(
        "SELECT region, SUM(revenue) AS revenue FROM sales GROUP BY region",
        allowed_tables=["sales"],
        schema={"sales": SCHEMA["sales"]},
        max_ast_nodes=3,
    )

    assert result.safe is False
    assert result.repairable is True
    assert result.reason_code == "query_too_complex"


def test_parent_grain_ctes_joined_on_unique_keys_are_fanout_safe() -> None:
    schema = {
        "orders": {
            "columns": [{"name": "id", "type": "INTEGER", "primary_key": True}],
            "foreign_keys": [],
        },
        "items": {
            "columns": [
                {"name": "order_id", "type": "INTEGER"},
                {"name": "amount", "type": "REAL"},
            ],
            "foreign_keys": [{"from_column": "order_id", "to_table": "orders", "to_column": "id"}],
        },
        "refunds": {
            "columns": [{"name": "order_id", "type": "INTEGER"}],
            "foreign_keys": [{"from_column": "order_id", "to_table": "orders", "to_column": "id"}],
        },
    }
    result = validate_sql(
        "WITH order_totals AS (SELECT order_id, SUM(amount) AS total FROM items GROUP BY order_id), "
        "refund_orders AS (SELECT DISTINCT order_id FROM refunds) "
        "SELECT COUNT(DISTINCT o.id) AS orders, AVG(t.total) AS average_total "
        "FROM orders o LEFT JOIN order_totals t ON t.order_id=o.id "
        "LEFT JOIN refund_orders r ON r.order_id=o.id",
        allowed_tables=list(schema),
        schema=schema,
    )

    assert result.safe is True


def test_expression_group_alias_is_inferred_as_derived_grain() -> None:
    result = validate_sql(
        "WITH monthly_detail AS ("
        "SELECT substr(order_date, 1, 7) AS month, region, SUM(revenue) AS revenue "
        "FROM sales GROUP BY substr(order_date, 1, 7), region), "
        "monthly_total AS ("
        "SELECT substr(order_date, 1, 7) AS month, SUM(revenue) AS total_revenue "
        "FROM sales GROUP BY substr(order_date, 1, 7)) "
        "SELECT d.month, d.region, d.revenue, t.total_revenue "
        "FROM monthly_detail d JOIN monthly_total t ON t.month=d.month",
        allowed_tables=["sales"],
        schema={"sales": SCHEMA["sales"]},
    )

    assert result.safe is True


def test_relative_period_query_cannot_invent_a_calendar_date() -> None:
    result = validate_sql(
        "SELECT SUM(revenue) FROM sales WHERE order_date >= '2024-01-01'",
        allowed_tables=["sales"],
        schema={"sales": SCHEMA["sales"]},
        question="Why did revenue decline recently?",
    )

    assert result.safe is False
    assert result.repairable is True
    assert result.reason_code == "invented_date_literal"


def test_explicit_calendar_year_allows_date_literals() -> None:
    result = validate_sql(
        "SELECT SUM(revenue) FROM sales WHERE order_date >= '2024-01-01'",
        allowed_tables=["sales"],
        schema={"sales": SCHEMA["sales"]},
        question="Show revenue since 2024.",
    )

    assert result.safe is True


def test_database_qualified_table_is_blocked() -> None:
    assert validate("SELECT region FROM main.sales").reason_code == "qualified_database"


def test_semicolon_inside_a_string_is_not_a_second_statement() -> None:
    result = validate("SELECT region FROM sales WHERE region = 'North;West'")
    assert result.safe is True
