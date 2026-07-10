from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any


def sales_rows(count: int = 600) -> list[tuple[Any, ...]]:
    rng = random.Random(1101)
    products = [
        ("Analytics Pro", "Software", 249.0),
        ("Workflow Hub", "Software", 179.0),
        ("Data Connect", "Software", 129.0),
        ("Edge Terminal", "Hardware", 459.0),
        ("Office Sensor", "Hardware", 89.0),
        ("Support Plus", "Services", 79.0),
        ("Migration Pack", "Services", 399.0),
        ("Team Training", "Services", 549.0),
    ]
    regions = ["North", "South", "East", "West"]
    channels = ["Direct", "Partner", "Online"]
    segments = ["SMB", "Mid-Market", "Enterprise"]
    start = date(2024, 1, 1)
    rows: list[tuple[Any, ...]] = []
    for index in range(1, count + 1):
        product, category, base_price = rng.choice(products)
        quantity = rng.randint(1, 8)
        unit_price = round(base_price * rng.uniform(0.9, 1.12), 2)
        revenue = round(quantity * unit_price, 2)
        rows.append(
            (
                index,
                (start + timedelta(days=rng.randrange(730))).isoformat(),
                product,
                category,
                rng.choice(regions),
                rng.choice(channels),
                quantity,
                unit_price,
                revenue,
                rng.choices(segments, weights=[45, 35, 20], k=1)[0],
            )
        )
    return rows


def employee_rows(count: int = 180) -> list[tuple[Any, ...]]:
    rng = random.Random(2202)
    departments = {
        "Engineering": ["Software Engineer", "Data Engineer", "Engineering Manager"],
        "Sales": ["Account Executive", "Sales Manager", "Sales Operations"],
        "Marketing": ["Growth Manager", "Content Strategist", "Analyst"],
        "Finance": ["Financial Analyst", "Controller", "Accountant"],
        "Operations": ["Operations Analyst", "Program Manager", "Coordinator"],
    }
    locations = ["Shanghai", "Beijing", "Shenzhen", "Singapore", "Remote"]
    risks = ["Low", "Medium", "High"]
    start = date(2016, 1, 1)
    rows: list[tuple[Any, ...]] = []
    for index in range(1, count + 1):
        department = rng.choice(list(departments))
        role = rng.choice(departments[department])
        salary_base = {
            "Engineering": 145_000,
            "Sales": 120_000,
            "Marketing": 105_000,
            "Finance": 115_000,
            "Operations": 98_000,
        }[department]
        score = round(rng.uniform(2.4, 5.0), 1)
        salary = int(salary_base * rng.uniform(0.72, 1.38))
        risk = rng.choices(risks, weights=[62, 27, 11], k=1)[0]
        rows.append(
            (
                index,
                f"Employee {index:03d}",
                department,
                role,
                rng.choice(locations),
                salary,
                score,
                (start + timedelta(days=rng.randrange(3200))).isoformat(),
                risk,
            )
        )
    return rows


def subscription_rows(count: int = 360) -> list[tuple[Any, ...]]:
    rng = random.Random(3303)
    plans = {"Starter": 49.0, "Growth": 149.0, "Scale": 399.0, "Enterprise": 899.0}
    countries = ["China", "Singapore", "Japan", "Australia", "United States", "Germany"]
    channels = ["Organic", "Paid Search", "Partner", "Outbound", "Referral"]
    start = date(2023, 1, 1)
    rows: list[tuple[Any, ...]] = []
    for index in range(1, count + 1):
        signup = start + timedelta(days=rng.randrange(900))
        plan = rng.choices(list(plans), weights=[35, 32, 23, 10], k=1)[0]
        churned = 1 if rng.random() < 0.22 else 0
        churn_date = signup + timedelta(days=rng.randrange(30, 500)) if churned else None
        rows.append(
            (
                index,
                signup.isoformat(),
                f"Subscriber {index:03d}",
                plan,
                plans[plan],
                "Churned" if churned else "Active",
                rng.choice(countries),
                rng.choice(channels),
                churned,
                churn_date.isoformat() if churn_date else None,
            )
        )
    return rows


def commerce_rows() -> dict[str, list[tuple[Any, ...]]]:
    rng = random.Random(4404)
    cities = ["Shanghai", "Beijing", "Shenzhen", "Chengdu", "Singapore", "Tokyo"]
    segments = ["SMB", "Mid-Market", "Enterprise"]
    customers: list[tuple[Any, ...]] = []
    for index in range(1, 181):
        customers.append(
            (
                index,
                f"Customer {index:03d}",
                f"customer{index:03d}@example.invalid",
                rng.choice(cities),
                rng.choices(segments, weights=[48, 34, 18], k=1)[0],
                (date(2022, 1, 1) + timedelta(days=rng.randrange(1000))).isoformat(),
            )
        )

    catalog = [
        ("Pulse Laptop", "Computing", 1299.0),
        ("Vector Laptop", "Computing", 999.0),
        ("Atlas Monitor", "Displays", 449.0),
        ("Canvas Monitor", "Displays", 329.0),
        ("Orbit Keyboard", "Accessories", 119.0),
        ("Drift Mouse", "Accessories", 79.0),
        ("Studio Camera", "Video", 279.0),
        ("Conference Bar", "Video", 849.0),
        ("Relay Headset", "Audio", 159.0),
        ("Focus Speaker", "Audio", 229.0),
        ("Dock Pro", "Accessories", 189.0),
        ("Secure Router", "Networking", 399.0),
    ]
    products: list[tuple[Any, ...]] = []
    product_id = 1
    for name, category, price in catalog:
        for suffix, factor in [("", 1.0), (" Mini", 0.78), (" Max", 1.28)]:
            products.append((product_id, f"{name}{suffix}", category, round(price * factor, 2)))
            product_id += 1

    orders: list[tuple[Any, ...]] = []
    order_items: list[tuple[Any, ...]] = []
    refunds: list[tuple[Any, ...]] = []
    start = date(2024, 1, 1)
    item_id = 1
    refund_id = 1
    methods = ["Card", "Bank Transfer", "Wallet"]
    channels = ["Online", "Direct", "Partner"]
    for order_id in range(1, 521):
        order_date = start + timedelta(days=rng.randrange(730))
        status = rng.choices(
            ["Completed", "Shipped", "Pending", "Cancelled"], weights=[58, 25, 10, 7], k=1
        )[0]
        orders.append(
            (
                order_id,
                rng.randint(1, len(customers)),
                order_date.isoformat(),
                status,
                rng.choice(methods),
                rng.choice(channels),
            )
        )
        order_total = 0.0
        for _ in range(rng.randint(1, 4)):
            product = rng.choice(products)
            quantity = rng.randint(1, 5)
            discount = rng.choice([0.0, 0.0, 0.05, 0.1, 0.15])
            unit_price = float(product[3])
            line_revenue = round(quantity * unit_price * (1 - discount), 2)
            order_items.append(
                (
                    item_id,
                    order_id,
                    product[0],
                    quantity,
                    unit_price,
                    discount,
                    line_revenue,
                )
            )
            item_id += 1
            order_total += line_revenue
        if status != "Cancelled" and rng.random() < 0.14:
            refunds.append(
                (
                    refund_id,
                    order_id,
                    (order_date + timedelta(days=rng.randint(2, 45))).isoformat(),
                    round(order_total * rng.uniform(0.2, 1.0), 2),
                    rng.choice(["Damaged", "Changed mind", "Late delivery", "Incorrect item"]),
                )
            )
            refund_id += 1
    return {
        "customers": customers,
        "products": products,
        "orders": orders,
        "order_items": order_items,
        "refunds": refunds,
    }
