from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from threading import RLock
from typing import Any, Literal, TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agent.prompts import (
    INSIGHT_PROMPT,
    REWRITE_PROMPT,
    SQL_GENERATION_PROMPT,
    SQL_REPAIR_PROMPT,
    TABLE_SELECTION_PROMPT,
)
from app.core.config import Settings
from app.core.errors import AppError


class QuestionRewrite(BaseModel):
    rewritten_question: str
    used_history: bool = False


class TableSelection(BaseModel):
    tables: list[str] = Field(default_factory=list)
    reason: str
    needs_clarification: bool = False
    clarification_question: str | None = None


class SqlGeneration(BaseModel):
    sql: str
    explanation: str
    selected_columns: list[str] = Field(default_factory=list)


class SqlRepair(BaseModel):
    sql: str
    explanation: str


class InsightOutput(BaseModel):
    insight: str


class BaseLLMClient(ABC):
    provider_name: str
    last_used_fallback: bool = False

    @abstractmethod
    def rewrite_question(self, question: str, history: list[dict[str, Any]]) -> QuestionRewrite: ...

    @abstractmethod
    def select_tables(
        self, dataset_id: str, question: str, table_catalog: dict[str, Any]
    ) -> TableSelection: ...

    @abstractmethod
    def generate_sql(
        self,
        dataset_id: str,
        question: str,
        selected_tables: list[str],
        schema: dict[str, Any],
        schema_context: str,
    ) -> SqlGeneration: ...

    @abstractmethod
    def repair_sql(
        self,
        dataset_id: str,
        question: str,
        sql: str,
        error_type: str,
        schema_context: str,
    ) -> SqlRepair: ...

    @abstractmethod
    def write_insight(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> InsightOutput: ...


def _normalized(text: str) -> str:
    lowered = re.sub(r"\s+", " ", text.strip().lower())
    translations = {
        "收入": " revenue ",
        "销售额": " revenue ",
        "趋势": " trend ",
        "月份": " month ",
        "月度": " monthly ",
        "地区": " region ",
        "区域": " region ",
        "渠道": " channel ",
        "产品": " product ",
        "类别": " category ",
        "部门": " department ",
        "薪资": " salary ",
        "工资": " salary ",
        "平均": " average ",
        "数量": " count ",
        "流失": " churn ",
        "退款": " refund ",
        "城市": " city ",
        "员工": " employee ",
        "订阅": " subscription ",
        "客户": " customer ",
        "最高": " highest ",
        "前五": " top five ",
        "分布": " distribution ",
    }
    for source, target in translations.items():
        lowered = lowered.replace(source, target)
    return re.sub(r"\s+", " ", lowered).strip()


class MockLLMClient(BaseLLMClient):
    provider_name = "mock"

    def rewrite_question(self, question: str, history: list[dict[str, Any]]) -> QuestionRewrite:
        normalized = _normalized(question)
        follow_up = normalized.startswith(
            ("what about", "how about", "and ", "only ", "那", "那么", "只看")
        )
        previous = next(
            (item.get("content", "") for item in reversed(history) if item.get("role") == "user"),
            "",
        )
        if follow_up and previous:
            return QuestionRewrite(
                rewritten_question=f"{previous} Follow-up constraint: {question}", used_history=True
            )
        return QuestionRewrite(rewritten_question=question, used_history=False)

    def select_tables(
        self, dataset_id: str, question: str, table_catalog: dict[str, Any]
    ) -> TableSelection:
        q = _normalized(question)
        available = list(table_catalog)
        ambiguous = any(
            phrase in q
            for phrase in (
                "tell me something",
                "analyze this",
                "do some analysis",
                "unknown table",
                "imaginary table",
                "nonexistent column",
                "unknown column",
            )
        )
        if ambiguous:
            return TableSelection(
                reason="The request does not identify a supported analytical concept.",
                needs_clarification=True,
                clarification_question="Which metric or business dimension should be analyzed?",
            )
        if dataset_id != "commerce":
            return TableSelection(tables=available[:1], reason="Single-table dataset selected.")

        selected: list[str] = []
        if any(term in q for term in ("product", "category")):
            selected.append("products")
        if any(term in q for term in ("revenue", "order value", "quantity", "product", "category")):
            selected.append("order_items")
        if any(
            term in q
            for term in (
                "order",
                "month",
                "trend",
                "channel",
                "refund",
                "city",
                "segment",
            )
        ):
            selected.append("orders")
        if any(term in q for term in ("city", "segment", "customer", "email")):
            selected.append("customers")
        if "refund" in q:
            selected.append("refunds")
        selected = [table for table in available if table in selected]
        if not selected:
            return TableSelection(
                reason="No Commerce table maps confidently to the request.",
                needs_clarification=True,
                clarification_question=(
                    "Should I analyze customers, products, orders, revenue, or refunds?"
                ),
            )
        return TableSelection(tables=selected, reason="Selected the minimum relationship path.")

    def generate_sql(
        self,
        dataset_id: str,
        question: str,
        selected_tables: list[str],
        schema: dict[str, Any],
        schema_context: str,
    ) -> SqlGeneration:
        del schema_context
        q = _normalized(question)
        if any(
            term in q for term in ("drop table", "delete from", "update rows", "attach database")
        ):
            verb = "DROP TABLE" if "drop" in q else "DELETE FROM"
            table = selected_tables[0] if selected_tables else "sales"
            return SqlGeneration(sql=f"{verb} {table}", explanation="Unsafe test request.")
        if dataset_id == "sales":
            return self._sales_sql(q)
        if dataset_id == "employees":
            return self._employees_sql(q)
        if dataset_id == "subscriptions":
            return self._subscriptions_sql(q)
        if dataset_id == "commerce":
            return self._commerce_sql(q)
        return self._uploaded_sql(q, schema)

    def _sales_sql(self, q: str) -> SqlGeneration:
        enterprise = "enterprise" in q
        where = " WHERE customer_segment = 'Enterprise'" if enterprise else ""
        if "repair" in q or "date_trunc" in q:
            return SqlGeneration(
                sql=(
                    "SELECT DATE_TRUNC('month', order_date) AS month, SUM(revenue) AS total_revenue "
                    "FROM sales GROUP BY 1 ORDER BY 1"
                ),
                explanation="Monthly aggregation repair demonstration.",
                selected_columns=["sales.order_date", "sales.revenue"],
            )
        if "atlantis" in q or "empty result" in q:
            return SqlGeneration(
                sql="SELECT region, SUM(revenue) AS total_revenue FROM sales WHERE region = 'Atlantis' GROUP BY region",
                explanation="Filter to the requested region.",
                selected_columns=["sales.region", "sales.revenue"],
            )
        if any(term in q for term in ("monthly", "month", "trend")):
            return SqlGeneration(
                sql=(
                    "SELECT strftime('%Y-%m', order_date) AS month, ROUND(SUM(revenue), 2) AS total_revenue "
                    f"FROM sales{where} GROUP BY month ORDER BY month"
                ),
                explanation="Aggregate revenue by calendar month.",
                selected_columns=["sales.order_date", "sales.revenue"],
            )
        if "region" in q:
            return SqlGeneration(
                sql=(
                    "SELECT region, ROUND(SUM(revenue), 2) AS total_revenue FROM sales"
                    f"{where} GROUP BY region ORDER BY total_revenue DESC"
                ),
                explanation="Aggregate revenue by region.",
                selected_columns=["sales.region", "sales.revenue"],
            )
        if "channel" in q and "average" in q:
            return SqlGeneration(
                sql="SELECT sales_channel, ROUND(AVG(revenue), 2) AS average_order_value FROM sales GROUP BY sales_channel ORDER BY average_order_value DESC",
                explanation="Calculate average order revenue by channel.",
                selected_columns=["sales.sales_channel", "sales.revenue"],
            )
        if "channel" in q:
            return SqlGeneration(
                sql="SELECT sales_channel, ROUND(SUM(revenue), 2) AS total_revenue FROM sales GROUP BY sales_channel ORDER BY total_revenue DESC",
                explanation="Aggregate revenue by sales channel.",
                selected_columns=["sales.sales_channel", "sales.revenue"],
            )
        if "product" in q:
            return SqlGeneration(
                sql="SELECT product, ROUND(SUM(revenue), 2) AS total_revenue FROM sales GROUP BY product ORDER BY total_revenue DESC LIMIT 5",
                explanation="Rank products by revenue.",
                selected_columns=["sales.product", "sales.revenue"],
            )
        if "category" in q or "distribution" in q:
            return SqlGeneration(
                sql="SELECT category, ROUND(SUM(revenue), 2) AS total_revenue FROM sales GROUP BY category ORDER BY total_revenue DESC",
                explanation="Aggregate revenue by category.",
                selected_columns=["sales.category", "sales.revenue"],
            )
        if "count" in q or "how many" in q:
            return SqlGeneration(
                sql="SELECT COUNT(*) AS total_rows FROM sales",
                explanation="Count sales records.",
            )
        return SqlGeneration(
            sql=f"SELECT ROUND(SUM(revenue), 2) AS total_revenue FROM sales{where}",
            explanation="Calculate total revenue.",
            selected_columns=["sales.revenue"],
        )

    def _employees_sql(self, q: str) -> SqlGeneration:
        if "salary" in q and "average" in q:
            return SqlGeneration(
                sql="SELECT department, ROUND(AVG(salary), 2) AS average_salary FROM employees GROUP BY department ORDER BY average_salary DESC",
                explanation="Aggregate salary by department; no individual values are returned.",
                selected_columns=["employees.department", "employees.salary"],
            )
        if "salary" in q:
            return SqlGeneration(
                sql="SELECT employee_name, department, salary FROM employees ORDER BY salary DESC LIMIT 100",
                explanation="Return individual salary values.",
                selected_columns=[
                    "employees.employee_name",
                    "employees.department",
                    "employees.salary",
                ],
            )
        if "location" in q or "headcount" in q:
            group = "location" if "location" in q else "department"
            return SqlGeneration(
                sql=f"SELECT {group}, COUNT(*) AS headcount FROM employees GROUP BY {group} ORDER BY headcount DESC",
                explanation=f"Count employees by {group}.",
                selected_columns=[f"employees.{group}"],
            )
        if "attrition" in q:
            return SqlGeneration(
                sql="SELECT department, ROUND(100.0 * SUM(CASE WHEN attrition_risk = 'High' THEN 1 ELSE 0 END) / COUNT(*), 2) AS high_risk_rate FROM employees GROUP BY department ORDER BY high_risk_rate DESC",
                explanation="Calculate high attrition-risk share by department.",
                selected_columns=["employees.department", "employees.attrition_risk"],
            )
        if "perform" in q and any(term in q for term in ("top", "highest", "employee")):
            return SqlGeneration(
                sql="SELECT employee_name, department, performance_score FROM employees ORDER BY performance_score DESC LIMIT 10",
                explanation="Rank individual employee performance.",
                selected_columns=[
                    "employees.employee_name",
                    "employees.department",
                    "employees.performance_score",
                ],
            )
        return SqlGeneration(
            sql="SELECT department, ROUND(AVG(performance_score), 2) AS average_performance FROM employees GROUP BY department ORDER BY average_performance DESC",
            explanation="Aggregate performance by department.",
            selected_columns=["employees.department", "employees.performance_score"],
        )

    def _subscriptions_sql(self, q: str) -> SqlGeneration:
        if "customer" in q and any(term in q for term in ("name", "list", "raw")):
            return SqlGeneration(
                sql="SELECT customer_name, plan, mrr, status FROM subscriptions LIMIT 100",
                explanation="Return row-level customer subscription data.",
                selected_columns=[
                    "subscriptions.customer_name",
                    "subscriptions.plan",
                    "subscriptions.mrr",
                    "subscriptions.status",
                ],
            )
        if "churn" in q:
            group = "acquisition_channel" if "channel" in q else "plan"
            return SqlGeneration(
                sql=f"SELECT {group}, ROUND(100.0 * SUM(churned) / COUNT(*), 2) AS churn_rate FROM subscriptions GROUP BY {group} ORDER BY churn_rate DESC",
                explanation=f"Calculate churn rate by {group}.",
                selected_columns=[f"subscriptions.{group}", "subscriptions.churned"],
            )
        if any(term in q for term in ("monthly", "month", "new subscription", "trend")):
            return SqlGeneration(
                sql="SELECT strftime('%Y-%m', signup_date) AS month, COUNT(*) AS new_subscriptions FROM subscriptions GROUP BY month ORDER BY month",
                explanation="Count new subscriptions by signup month.",
                selected_columns=["subscriptions.signup_date"],
            )
        if "country" in q:
            return SqlGeneration(
                sql="SELECT country, COUNT(*) AS active_subscriptions FROM subscriptions WHERE status = 'Active' GROUP BY country ORDER BY active_subscriptions DESC",
                explanation="Count active subscriptions by country.",
                selected_columns=["subscriptions.country", "subscriptions.status"],
            )
        return SqlGeneration(
            sql="SELECT plan, ROUND(SUM(mrr), 2) AS total_mrr FROM subscriptions WHERE status = 'Active' GROUP BY plan ORDER BY total_mrr DESC",
            explanation="Aggregate active MRR by plan.",
            selected_columns=["subscriptions.plan", "subscriptions.mrr", "subscriptions.status"],
        )

    def _commerce_sql(self, q: str) -> SqlGeneration:
        completed = "o.status != 'Cancelled'"
        if "email" in q:
            return SqlGeneration(
                sql="SELECT customer_name, email, city, segment FROM customers LIMIT 100",
                explanation="Return raw customer identifiers.",
                selected_columns=[
                    "customers.customer_name",
                    "customers.email",
                    "customers.city",
                    "customers.segment",
                ],
            )
        if "refund" in q and "category" in q:
            return SqlGeneration(
                sql=(
                    "SELECT p.category, ROUND(100.0 * COALESCE(SUM(r.refund_amount), 0) / "
                    "NULLIF(SUM(oi.line_revenue), 0), 2) AS refund_rate FROM products p "
                    "JOIN order_items oi ON oi.product_id = p.id JOIN orders o ON o.id = oi.order_id "
                    "LEFT JOIN refunds r ON r.order_id = o.id GROUP BY p.category ORDER BY refund_rate DESC"
                ),
                explanation="Compare refunded amount with line revenue by product category.",
                selected_columns=[
                    "products.category",
                    "refunds.refund_amount",
                    "order_items.line_revenue",
                ],
            )
        if "refund" in q and "month" in q:
            return SqlGeneration(
                sql=(
                    "WITH revenue_by_month AS (SELECT strftime('%Y-%m', o.order_date) AS month, "
                    "SUM(oi.line_revenue) AS revenue FROM orders o JOIN order_items oi ON oi.order_id = o.id "
                    "WHERE o.status != 'Cancelled' GROUP BY month), refund_by_month AS "
                    "(SELECT strftime('%Y-%m', refund_date) AS month, SUM(refund_amount) AS refund_amount "
                    "FROM refunds GROUP BY month) SELECT rbm.month, ROUND(rbm.revenue, 2) AS revenue, "
                    "ROUND(COALESCE(fbm.refund_amount, 0), 2) AS refund_amount FROM revenue_by_month rbm "
                    "LEFT JOIN refund_by_month fbm ON fbm.month = rbm.month ORDER BY rbm.month"
                ),
                explanation="Join monthly revenue and refund aggregates.",
                selected_columns=[
                    "orders.order_date",
                    "order_items.line_revenue",
                    "refunds.refund_date",
                    "refunds.refund_amount",
                ],
            )
        if (
            "city" in q
            and any(term in q for term in ("order", "most", "count"))
            and "revenue" not in q
        ):
            return SqlGeneration(
                sql="SELECT c.city, COUNT(*) AS order_count FROM customers c JOIN orders o ON o.customer_id = c.id GROUP BY c.city ORDER BY order_count DESC LIMIT 10",
                explanation="Count orders by customer city.",
                selected_columns=["customers.city", "orders.id"],
            )
        if "city" in q:
            return SqlGeneration(
                sql=(
                    "SELECT c.city, ROUND(SUM(oi.line_revenue), 2) AS total_revenue FROM customers c "
                    "JOIN orders o ON o.customer_id = c.id JOIN order_items oi ON oi.order_id = o.id "
                    f"WHERE {completed} GROUP BY c.city ORDER BY total_revenue DESC LIMIT 10"
                ),
                explanation="Aggregate order-item revenue through customers and orders by city.",
                selected_columns=["customers.city", "order_items.line_revenue", "orders.status"],
            )
        if "segment" in q and "average" in q:
            return SqlGeneration(
                sql=(
                    "WITH order_totals AS (SELECT o.id, o.customer_id, SUM(oi.line_revenue) AS order_value "
                    "FROM orders o JOIN order_items oi ON oi.order_id = o.id WHERE o.status != 'Cancelled' "
                    "GROUP BY o.id, o.customer_id) SELECT c.segment, ROUND(AVG(ot.order_value), 2) AS "
                    "average_order_value FROM customers c JOIN order_totals ot ON ot.customer_id = c.id "
                    "GROUP BY c.segment ORDER BY average_order_value DESC"
                ),
                explanation="Average completed order totals by customer segment.",
                selected_columns=[
                    "customers.segment",
                    "orders.id",
                    "orders.customer_id",
                    "orders.status",
                    "order_items.line_revenue",
                ],
            )
        if "status" in q and ("breakdown" in q or "distribution" in q):
            return SqlGeneration(
                sql="SELECT status, COUNT(*) AS order_count FROM orders GROUP BY status ORDER BY order_count DESC",
                explanation="Count orders by status.",
                selected_columns=["orders.status"],
            )
        if "channel" in q:
            return SqlGeneration(
                sql=(
                    "SELECT o.sales_channel, ROUND(SUM(oi.line_revenue), 2) AS total_revenue FROM orders o "
                    "JOIN order_items oi ON oi.order_id = o.id WHERE o.status != 'Cancelled' "
                    "GROUP BY o.sales_channel ORDER BY total_revenue DESC"
                ),
                explanation="Aggregate completed order revenue by sales channel.",
                selected_columns=[
                    "orders.sales_channel",
                    "orders.status",
                    "order_items.line_revenue",
                ],
            )
        if any(term in q for term in ("monthly", "month", "trend")):
            return SqlGeneration(
                sql=(
                    "SELECT strftime('%Y-%m', o.order_date) AS month, "
                    "ROUND(SUM(oi.line_revenue), 2) AS total_revenue FROM orders o "
                    "JOIN order_items oi ON oi.order_id = o.id WHERE o.status != 'Cancelled' "
                    "GROUP BY month ORDER BY month"
                ),
                explanation="Aggregate completed order revenue by month.",
                selected_columns=["orders.order_date", "orders.status", "order_items.line_revenue"],
            )
        return SqlGeneration(
            sql=(
                "SELECT p.product_name, ROUND(SUM(oi.line_revenue), 2) AS total_revenue "
                "FROM products p JOIN order_items oi ON oi.product_id = p.id "
                "GROUP BY p.product_name ORDER BY total_revenue DESC LIMIT 5"
            ),
            explanation="Rank products by summed line revenue.",
            selected_columns=["products.product_name", "order_items.line_revenue"],
        )

    def _uploaded_sql(self, q: str, schema: dict[str, Any]) -> SqlGeneration:
        table = next(iter(schema), "data")
        columns = [column["name"] for column in schema.get(table, {}).get("columns", [])]
        numeric = [
            column["name"]
            for column in schema.get(table, {}).get("columns", [])
            if column.get("type", "").upper() in {"INTEGER", "REAL", "FLOAT", "NUMERIC"}
        ]
        matched = [column for column in columns if column.lower().replace("_", " ") in q]
        if "count" in q or "how many" in q:
            return SqlGeneration(
                sql=f'SELECT COUNT(*) AS total_rows FROM "{table}"', explanation="Count rows."
            )
        if "average" in q and numeric:
            target = next((column for column in matched if column in numeric), numeric[0])
            category = next((column for column in matched if column != target), None)
            if category:
                return SqlGeneration(
                    sql=f'SELECT "{category}", AVG("{target}") AS average_{target} FROM "{table}" GROUP BY "{category}" ORDER BY average_{target} DESC',
                    explanation="Calculate a grouped average.",
                    selected_columns=[f"{table}.{category}", f"{table}.{target}"],
                )
            return SqlGeneration(
                sql=f'SELECT AVG("{target}") AS average_{target} FROM "{table}"',
                explanation="Calculate an average.",
                selected_columns=[f"{table}.{target}"],
            )
        if "sum" in q or "total" in q:
            target = next(
                (column for column in matched if column in numeric), numeric[0] if numeric else None
            )
            if target:
                return SqlGeneration(
                    sql=f'SELECT SUM("{target}") AS total_{target} FROM "{table}"',
                    explanation="Calculate a total.",
                    selected_columns=[f"{table}.{target}"],
                )
        chosen = matched[:5] or columns[:5]
        quoted = ", ".join(f'"{column}"' for column in chosen)
        return SqlGeneration(
            sql=f'SELECT {quoted} FROM "{table}" LIMIT 100',
            explanation="Return the requested uploaded data columns.",
            selected_columns=[f"{table}.{column}" for column in chosen],
        )

    def repair_sql(
        self,
        dataset_id: str,
        question: str,
        sql: str,
        error_type: str,
        schema_context: str,
    ) -> SqlRepair:
        del dataset_id, question, error_type, schema_context
        repaired = re.sub(
            r"DATE_TRUNC\('month',\s*([a-zA-Z0-9_.]+)\)",
            r"strftime('%Y-%m', \1)",
            sql,
            flags=re.IGNORECASE,
        )
        return SqlRepair(sql=repaired, explanation="Replaced a non-SQLite date function.")

    def write_insight(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> InsightOutput:
        del sql
        if not rows:
            return InsightOutput(
                insight=(
                    "Observation: No rows matched the validated query. Limitation: The result cannot "
                    "support a comparison or causal interpretation."
                )
            )
        first = rows[0]
        visible = ", ".join(f"{key}={first.get(key)}" for key in columns[:3])
        return InsightOutput(
            insight=(
                f"Observation: The query returned {len(rows)} row(s); the first ranked result is {visible}. "
                "Cautious interpretation: this highlights the strongest pattern in the returned slice. "
                "Limitation: the result describes the selected data and does not establish causality."
            )
        )


StructuredT = TypeVar("StructuredT", bound=BaseModel)


class OpenAICompatibleLLMClient(BaseLLMClient):
    provider_name = "openai_compatible"

    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider_name: str = "openai_compatible",
        extra_body: Mapping[str, Any] | None = None,
        allow_mock_fallback: bool = True,
        structured_output_method: Literal["function_calling", "json_schema"] = "function_calling",
        max_tokens: int | None = None,
    ) -> None:
        resolved_key = api_key if api_key is not None else settings.openai_api_key
        if not resolved_key:
            raise AppError(
                "llm_auth_error",
                "OPENAI_API_KEY is required for the real provider.",
                status_code=503,
            )
        self.provider_name = provider_name
        kwargs: dict[str, Any] = {
            "api_key": resolved_key,
            "model": model or settings.openai_model,
            "temperature": 0,
            "timeout": settings.llm_timeout_seconds,
            "max_retries": settings.llm_max_retries,
        }
        resolved_base_url = base_url if base_url is not None else settings.openai_base_url
        if resolved_base_url:
            kwargs["base_url"] = resolved_base_url
        if extra_body:
            kwargs["extra_body"] = dict(extra_body)
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        self.model = ChatOpenAI(**kwargs)
        self.fallback = MockLLMClient()
        self.last_used_fallback = False
        self.allow_mock_fallback = allow_mock_fallback
        self.structured_output_method = structured_output_method

    @staticmethod
    def _provider_status_code(error: Exception) -> int | None:
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(error, "response", None)
        response_status = getattr(response, "status_code", None)
        return response_status if isinstance(response_status, int) else None

    @classmethod
    def _raise_provider_error(cls, error: Exception) -> None:
        name = type(error).__name__.lower()
        message = str(error).lower()
        status_code = cls._provider_status_code(error)
        if (
            status_code in {401, 403}
            or "authentication" in name
            or "permission" in name
            or "401" in message
            or "403" in message
        ):
            raise AppError(
                "llm_auth_error",
                "The configured model provider rejected authentication.",
                status_code=401,
            ) from error
        if status_code == 402 or "insufficient balance" in message:
            raise AppError(
                "llm_balance_error",
                "The model provider account has insufficient balance.",
                status_code=402,
            ) from error
        if status_code == 429 or "ratelimit" in name or "rate limit" in message:
            raise AppError(
                "llm_rate_limit",
                "The model provider rate limit was reached.",
                status_code=429,
            ) from error
        if "timeout" in name or "timed out" in message:
            raise AppError(
                "llm_timeout", "The model provider timed out.", status_code=504
            ) from error
        if "connection" in name or "network" in name:
            raise AppError(
                "llm_network_error", "The model provider is unavailable.", status_code=503
            ) from error
        if status_code in {400, 422}:
            raise AppError(
                "llm_request_error",
                "The model provider rejected the request format.",
                status_code=502,
            ) from error
        if status_code is not None and status_code >= 500:
            raise AppError(
                "llm_provider_error",
                "The model provider returned a service error.",
                status_code=503,
            ) from error

    def _invoke_structured(
        self,
        prompt: Any,
        schema: type[StructuredT],
        inputs: dict[str, Any],
        fallback: Callable[[], StructuredT],
        *,
        request_kwargs: Mapping[str, Any] | None = None,
    ) -> StructuredT:
        self.last_used_fallback = False
        bound_kwargs = dict(request_kwargs or {})
        try:
            chain = prompt | self.model.with_structured_output(
                schema, method=self.structured_output_method, **bound_kwargs
            )
            result = chain.invoke(inputs)
            return result if isinstance(result, schema) else schema.model_validate(result)
        except Exception as first_error:
            self._raise_provider_error(first_error)
            recovery_error: Exception | None = None
            try:
                message = (prompt | self.model.bind(**bound_kwargs)).invoke(inputs)
                content = (
                    message.content if isinstance(message.content, str) else str(message.content)
                )
                match = re.search(r"\{.*\}", content, flags=re.DOTALL)
                if match:
                    return schema.model_validate(json.loads(match.group(0)))
            except Exception as caught_recovery_error:
                recovery_error = caught_recovery_error
                self._raise_provider_error(caught_recovery_error)
            if not self.allow_mock_fallback:
                raise AppError(
                    "local_model_error",
                    "The local model did not return compatible structured output. "
                    "Check the Model ID and tool-calling support.",
                    status_code=502,
                ) from (recovery_error or first_error)
            try:
                self.last_used_fallback = True
                return fallback()
            except Exception as fallback_error:
                raise AppError(
                    "llm_invalid_output", "The model returned invalid structured output."
                ) from (fallback_error or first_error)

    def rewrite_question(self, question: str, history: list[dict[str, Any]]) -> QuestionRewrite:
        return self._invoke_structured(
            REWRITE_PROMPT,
            QuestionRewrite,
            {"history": json.dumps(history[-12:]), "question": question},
            lambda: self.fallback.rewrite_question(question, history),
            request_kwargs=(
                {
                    "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
                    "reasoning_effort": "none",
                }
                if self.provider_name == "local"
                else None
            ),
        )

    def select_tables(
        self, dataset_id: str, question: str, table_catalog: dict[str, Any]
    ) -> TableSelection:
        return self._invoke_structured(
            TABLE_SELECTION_PROMPT,
            TableSelection,
            {"question": question, "table_catalog": json.dumps(table_catalog)},
            lambda: self.fallback.select_tables(dataset_id, question, table_catalog),
        )

    def generate_sql(
        self,
        dataset_id: str,
        question: str,
        selected_tables: list[str],
        schema: dict[str, Any],
        schema_context: str,
    ) -> SqlGeneration:
        return self._invoke_structured(
            SQL_GENERATION_PROMPT,
            SqlGeneration,
            {
                "dataset_id": dataset_id,
                "question": question,
                "schema_context": schema_context,
            },
            lambda: self.fallback.generate_sql(
                dataset_id, question, selected_tables, schema, schema_context
            ),
        )

    def repair_sql(
        self,
        dataset_id: str,
        question: str,
        sql: str,
        error_type: str,
        schema_context: str,
    ) -> SqlRepair:
        return self._invoke_structured(
            SQL_REPAIR_PROMPT,
            SqlRepair,
            {
                "dataset_id": dataset_id,
                "question": question,
                "schema_context": schema_context,
                "sql": sql,
                "error_type": error_type,
            },
            lambda: self.fallback.repair_sql(dataset_id, question, sql, error_type, schema_context),
        )

    def write_insight(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> InsightOutput:
        return self._invoke_structured(
            INSIGHT_PROMPT,
            InsightOutput,
            {
                "question": question,
                "sql": sql,
                "columns": json.dumps(columns),
                "rows": json.dumps(rows[:20]),
            },
            lambda: self.fallback.write_insight(question, sql, columns, rows),
        )


def get_llm_client(settings: Settings) -> BaseLLMClient:
    if settings.llm_provider == "mock":
        return MockLLMClient()
    return OpenAICompatibleLLMClient(settings)


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_MAX_TOKENS = 2048
LOCAL_MODEL_MAX_TOKENS = 2048


def get_deepseek_client(settings: Settings, api_key: str) -> BaseLLMClient:
    return OpenAICompatibleLLMClient(
        settings,
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        model=DEEPSEEK_MODEL,
        provider_name="deepseek",
        extra_body={
            "thinking": {"type": "disabled"},
            "max_tokens": DEEPSEEK_MAX_TOKENS,
        },
    )


def get_local_model_client(settings: Settings, base_url: str, model: str) -> BaseLLMClient:
    return OpenAICompatibleLLMClient(
        settings,
        api_key=settings.openai_api_key or "local",
        base_url=base_url,
        model=model,
        provider_name="local",
        allow_mock_fallback=False,
        structured_output_method="json_schema",
        max_tokens=LOCAL_MODEL_MAX_TOKENS,
    )


class LLMClientResolver:
    """Resolve an ephemeral model client without putting credentials in graph state."""

    def __init__(self, default_client: BaseLLMClient) -> None:
        self.default_client = default_client
        self._temporary_clients: dict[str, BaseLLMClient] = {}
        self._lock = RLock()

    def for_request(self, request_id: str) -> BaseLLMClient:
        with self._lock:
            return self._temporary_clients.get(request_id, self.default_client)

    @contextmanager
    def temporary(self, request_id: str, client: BaseLLMClient):
        with self._lock:
            if request_id in self._temporary_clients:
                raise AppError(
                    "internal_error",
                    "A temporary model client is already active for this request.",
                    status_code=409,
                )
            self._temporary_clients[request_id] = client
        try:
            yield
        finally:
            with self._lock:
                if self._temporary_clients.get(request_id) is client:
                    self._temporary_clients.pop(request_id, None)

    @property
    def temporary_count(self) -> int:
        with self._lock:
            return len(self._temporary_clients)
