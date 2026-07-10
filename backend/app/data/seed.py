from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.data.sample_data import commerce_rows, employee_rows, sales_rows, subscription_rows
from app.data.schema_reader import inspect_database
from app.models import Dataset


@dataclass(frozen=True)
class BuiltinDefinition:
    id: str
    name: str
    description: str
    filename: str
    tables: tuple[str, ...]
    sensitive_columns: frozenset[str]
    suggestions: tuple[str, ...]


BUILTINS = {
    "sales": BuiltinDefinition(
        "sales",
        "Sales Performance",
        "Two years of product, region, channel, and segment revenue.",
        "sales.sqlite3",
        ("sales",),
        frozenset(),
        (
            "Which region generated the most revenue?",
            "Show monthly revenue trend.",
            "Compare revenue by sales channel.",
            "What is average order revenue by customer segment?",
        ),
    ),
    "employees": BuiltinDefinition(
        "employees",
        "People Operations",
        "Workforce distribution, performance, compensation, and attrition risk.",
        "employees.sqlite3",
        ("employees",),
        frozenset({"employees.employee_name", "employees.salary"}),
        (
            "What is the average salary by department?",
            "Show headcount by location.",
            "Which departments have the highest attrition risk?",
            "Show average performance score by department.",
        ),
    ),
    "subscriptions": BuiltinDefinition(
        "subscriptions",
        "SaaS Subscriptions",
        "Subscription plans, recurring revenue, acquisition, status, and churn.",
        "subscriptions.sqlite3",
        ("subscriptions",),
        frozenset({"subscriptions.customer_name"}),
        (
            "What is total MRR by plan?",
            "Show churn rate by acquisition channel.",
            "Show monthly new subscriptions.",
            "Compare active subscriptions by country.",
        ),
    ),
    "commerce": BuiltinDefinition(
        "commerce",
        "Commerce Operations",
        "Relational customers, catalog, orders, line items, and refunds.",
        "commerce.sqlite3",
        ("customers", "products", "orders", "order_items", "refunds"),
        frozenset({"customers.customer_name", "customers.email"}),
        (
            "Which five products generated the most revenue?",
            "Show monthly revenue trend.",
            "Which city has the highest order revenue?",
            "What is the refund rate by product category?",
            "Compare revenue and refund amount by month.",
        ),
    ),
}


def _ensure_rows(
    connection: sqlite3.Connection,
    table: str,
    expected: int,
    insert_sql: str,
    factory: Callable[[], list[tuple[object, ...]]],
) -> None:
    current = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    if current == expected:
        return
    connection.execute(f'DELETE FROM "{table}"')
    connection.executemany(insert_sql, factory())


def _seed_sales(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY, order_date TEXT NOT NULL, product TEXT NOT NULL,
                category TEXT NOT NULL, region TEXT NOT NULL, sales_channel TEXT NOT NULL,
                quantity INTEGER NOT NULL, unit_price REAL NOT NULL, revenue REAL NOT NULL,
                customer_segment TEXT NOT NULL
            )"""
        )
        _ensure_rows(
            connection,
            "sales",
            600,
            "INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            sales_rows,
        )


def _seed_employees(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY, employee_name TEXT NOT NULL, department TEXT NOT NULL,
                role TEXT NOT NULL, location TEXT NOT NULL, salary INTEGER NOT NULL,
                performance_score REAL NOT NULL, hire_date TEXT NOT NULL,
                attrition_risk TEXT NOT NULL
            )"""
        )
        _ensure_rows(
            connection,
            "employees",
            180,
            "INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            employee_rows,
        )


def _seed_subscriptions(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY, signup_date TEXT NOT NULL, customer_name TEXT NOT NULL,
                plan TEXT NOT NULL, mrr REAL NOT NULL, status TEXT NOT NULL, country TEXT NOT NULL,
                acquisition_channel TEXT NOT NULL, churned INTEGER NOT NULL, churn_date TEXT
            )"""
        )
        _ensure_rows(
            connection,
            "subscriptions",
            360,
            "INSERT INTO subscriptions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            subscription_rows,
        )


def _seed_commerce(path: Path) -> None:
    rows = commerce_rows()
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY, customer_name TEXT NOT NULL, email TEXT NOT NULL,
                city TEXT NOT NULL, segment TEXT NOT NULL, signup_date TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY, product_name TEXT NOT NULL, category TEXT NOT NULL,
                unit_price REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, order_date TEXT NOT NULL,
                status TEXT NOT NULL, payment_method TEXT NOT NULL, sales_channel TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL, unit_price REAL NOT NULL, discount REAL NOT NULL,
                line_revenue REAL NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            );
            CREATE TABLE IF NOT EXISTS refunds (
                id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, refund_date TEXT NOT NULL,
                refund_amount REAL NOT NULL, reason TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );
            """
        )
        expected = {table: len(values) for table, values in rows.items()}
        current = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in rows
        }
        if current == expected:
            return
        for table in ("refunds", "order_items", "orders", "products", "customers"):
            connection.execute(f'DELETE FROM "{table}"')
        connection.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", rows["customers"])
        connection.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", rows["products"])
        connection.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", rows["orders"])
        connection.executemany(
            "INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?, ?)", rows["order_items"]
        )
        connection.executemany("INSERT INTO refunds VALUES (?, ?, ?, ?, ?)", rows["refunds"])


SEEDERS = {
    "sales": _seed_sales,
    "employees": _seed_employees,
    "subscriptions": _seed_subscriptions,
    "commerce": _seed_commerce,
}


def seed_builtin_datasets(session: Session, settings: Settings) -> None:
    settings.ensure_runtime_dirs()
    for dataset_id, definition in BUILTINS.items():
        path = (settings.datasets_dir / definition.filename).resolve()
        SEEDERS[dataset_id](path)
        schema = inspect_database(path, sensitive_columns=set(definition.sensitive_columns))
        row_count = 0
        with closing(sqlite3.connect(path)) as connection:
            row_count = sum(
                connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in definition.tables
            )
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            dataset = Dataset(id=dataset_id, source_type="sample", is_builtin=True)
            session.add(dataset)
        dataset.name = definition.name
        dataset.description = definition.description
        dataset.db_path = str(path)
        dataset.tables_json = json.dumps(list(definition.tables))
        dataset.schema_json = json.dumps(schema)
        dataset.column_mapping_json = "[]"
        dataset.row_count = row_count
        dataset.is_builtin = True
    session.flush()
