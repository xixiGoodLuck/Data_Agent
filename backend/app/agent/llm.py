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

from app.agent.language import ResponseLanguage, is_chinese
from app.agent.prompts import (
    ANALYSIS_EVALUATION_PROMPT,
    ANALYSIS_INTENT_PROMPT,
    ANALYSIS_PLAN_PROMPT,
    FINAL_ANALYSIS_PROMPT,
    INSIGHT_PROMPT,
    REWRITE_PROMPT,
    SQL_GENERATION_PROMPT,
    SQL_REPAIR_PROMPT,
    TABLE_SELECTION_PROMPT,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.query import (
    MAX_ANALYSIS_STEPS,
    AnalysisEvaluation,
    AnalysisIntent,
    AnalysisPlan,
    AnalysisStep,
    CriticResult,
    Evidence,
    FinalAnalysis,
    Finding,
    NextAnalysisDecision,
)


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
    def rewrite_question(
        self,
        question: str,
        history: list[dict[str, Any]],
        response_language: ResponseLanguage = "en",
    ) -> QuestionRewrite: ...

    @abstractmethod
    def understand_analysis_intent(
        self, question: str, response_language: ResponseLanguage = "en"
    ) -> AnalysisIntent: ...

    @abstractmethod
    def create_analysis_plan(
        self,
        question: str,
        intent: AnalysisIntent,
        response_language: ResponseLanguage = "en",
    ) -> AnalysisPlan: ...

    @abstractmethod
    def evaluate_analysis(
        self,
        intent: AnalysisIntent,
        plan: AnalysisPlan,
        evidence: list[Evidence],
        response_language: ResponseLanguage = "en",
    ) -> AnalysisEvaluation: ...

    @abstractmethod
    def synthesize_analysis(
        self,
        question: str,
        intent: AnalysisIntent,
        plan: AnalysisPlan,
        evidence: list[Evidence],
        critic: CriticResult | None,
        evidence_insufficient: bool,
        response_language: ResponseLanguage = "en",
    ) -> FinalAnalysis: ...

    @abstractmethod
    def select_tables(
        self,
        dataset_id: str,
        question: str,
        table_catalog: dict[str, Any],
        response_language: ResponseLanguage = "en",
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
        response_language: ResponseLanguage = "en",
    ) -> InsightOutput: ...


def _normalized(text: str) -> str:
    lowered = re.sub(r"\s+", " ", text.strip().lower())
    translations = {
        "平均订单金额": " average order value ",
        "订单量": " order volume ",
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


def _find_change(key_values: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for key, value in key_values.items():
        if (
            key.endswith("_change_pct")
            and any(name in key for name in names)
            and isinstance(value, int | float)
            and not isinstance(value, bool)
        ):
            return float(value)
    return None


class MockLLMClient(BaseLLMClient):
    provider_name = "mock"

    def rewrite_question(
        self,
        question: str,
        history: list[dict[str, Any]],
        response_language: ResponseLanguage = "en",
    ) -> QuestionRewrite:
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
                rewritten_question=(
                    f"{previous} 后续约束: {question}"
                    if is_chinese(response_language)
                    else f"{previous} Follow-up constraint: {question}"
                ),
                used_history=True,
            )
        return QuestionRewrite(rewritten_question=question, used_history=False)

    def understand_analysis_intent(
        self, question: str, response_language: ResponseLanguage = "en"
    ) -> AnalysisIntent:
        q = question.lower()
        exploratory_terms = (
            "analyze this dataset",
            "analyse this dataset",
            "what should i pay attention to",
            "what is worth investigating",
            "explore",
            "exploratory",
            "分析这个数据",
            "分析这份数据",
            "值得关注",
            "有什么问题",
        )
        diagnostic_terms = (
            "why",
            "root cause",
            "diagnose",
            "diagnostic",
            "driver",
            "what caused",
            "explain the decline",
            "为什么",
            "原因",
            "诊断",
            "驱动因素",
        )
        if any(term in q for term in exploratory_terms):
            analysis_type = "exploratory"
        elif any(term in q for term in diagnostic_terms):
            analysis_type = "diagnostic"
        elif any(term in q for term in ("trend", "monthly", "month", "趋势", "月度", "每月")):
            analysis_type = "trend"
        elif any(
            term in q for term in ("highest", "lowest", "top ", "rank", "最高", "最低", "排名")
        ):
            analysis_type = "ranking"
        elif any(term in q for term in ("compare", "comparison", "versus", " vs ", "对比", "比较")):
            analysis_type = "comparison"
        else:
            analysis_type = "lookup"

        metric_terms = (
            ("revenue", ("revenue", "income", "sales", "收入", "销售额")),
            ("refund_amount", ("refund", "退款")),
            ("order_count", ("order count", "orders", "订单数", "订单数量")),
            ("average_order_value", ("average order", "aov", "平均订单")),
            ("mrr", ("mrr",)),
            ("salary", ("salary", "薪资", "工资")),
        )
        dimension_terms = (
            ("city", ("city", "城市")),
            ("month", ("monthly", "month", "月度", "每月", "月份")),
            ("category", ("category", "类别")),
            ("product", ("product", "商品", "产品")),
            ("region", ("region", "地区", "区域")),
            ("channel", ("channel", "渠道")),
        )
        metrics = [name for name, terms in metric_terms if any(term in q for term in terms)]
        dimensions = [name for name, terms in dimension_terms if any(term in q for term in terms)]
        needs_multi_step = analysis_type in {"diagnostic", "exploratory"}
        return AnalysisIntent(
            objective=question.strip(),
            analysis_type=analysis_type,
            metrics=metrics,
            dimensions=dimensions,
            filters=[],
            time_range=("最近期间" if is_chinese(response_language) else "recent period")
            if any(term in q for term in ("recent", "最近"))
            else None,
            comparison=("期间对比" if is_chinese(response_language) else "period over period")
            if analysis_type == "diagnostic"
            else None,
            desired_grain="month"
            if "month" in dimensions
            else dimensions[0]
            if dimensions
            else None,
            needs_multi_step=needs_multi_step,
            reason=(
                "该问题需要根据已有证据继续开展后续分析。"
                if needs_multi_step and is_chinese(response_language)
                else "The question needs evidence-guided follow-up analysis."
                if needs_multi_step
                else "一次经过校验的查询即可回答该问题。"
                if is_chinese(response_language)
                else "One validated query can answer the question."
            ),
        )

    def create_analysis_plan(
        self,
        question: str,
        intent: AnalysisIntent,
        response_language: ResponseLanguage = "en",
    ) -> AnalysisPlan:
        metric = intent.metrics[0].replace("_", " ") if intent.metrics else "the target metric"
        if is_chinese(response_language):
            metric = {
                "revenue": "收入",
                "refund_amount": "退款金额",
                "order_count": "订单量",
                "average_order_value": "平均订单金额",
                "mrr": "月度经常性收入",
                "salary": "薪资",
            }.get(intent.metrics[0] if intent.metrics else "", "目标指标")
        if intent.analysis_type == "exploratory":
            steps = [
                AnalysisStep(
                    id="step_1",
                    question=(
                        f"汇总{metric}的整体分布。"
                        if is_chinese(response_language)
                        else f"Summarize the overall distribution of {metric}."
                    ),
                    purpose=(
                        "先建立基线, 再选择深入分析方向。"
                        if is_chinese(response_language)
                        else "Establish a baseline before selecting a deeper direction."
                    ),
                ),
                AnalysisStep(
                    id="step_2",
                    question=(
                        f"哪些细分维度的{metric}偏差最大?"
                        if is_chinese(response_language)
                        else f"Which segments show the largest deviations in {metric}?"
                    ),
                    purpose=(
                        "从基线中识别证据支持最强的异常模式。"
                        if is_chinese(response_language)
                        else "Identify the strongest evidence-backed pattern from the baseline."
                    ),
                ),
                AnalysisStep(
                    id="step_3",
                    question=(
                        "当前观察到的偏差最支持哪一个后续问题?"
                        if is_chinese(response_language)
                        else "What follow-up question is best supported by the observed deviation?"
                    ),
                    purpose=(
                        "根据证据选择下一方向, 而不是机械枚举维度。"
                        if is_chinese(response_language)
                        else "Choose the next direction from evidence instead of enumerating dimensions."
                    ),
                ),
            ]
        else:
            steps = [
                AnalysisStep(
                    id="step_1",
                    question=(
                        f"查看{metric}的月度趋势, 确认是否确实下降。"
                        if is_chinese(response_language)
                        else f"Show the monthly trend for {metric} to verify whether it declined."
                    ),
                    purpose=(
                        "确认所述变化是否存在, 并量化其发生时间。"
                        if is_chinese(response_language)
                        else "Confirm that the reported change exists and quantify its timing."
                    ),
                ),
                AnalysisStep(
                    id="step_2",
                    question=(
                        f"将{metric}变化拆解为订单量与平均订单金额。"
                        if is_chinese(response_language)
                        else f"Decompose the change in {metric} into volume and value components."
                    ),
                    purpose=(
                        "区分造成该变化的主要量价因素。"
                        if is_chinese(response_language)
                        else "Separate the primary mathematical contributors to the change."
                    ),
                ),
                AnalysisStep(
                    id="step_3",
                    question=(
                        "根据已有贡献证据, 下一步应调查哪个业务维度?"
                        if is_chinese(response_language)
                        else "Which business dimension should be investigated based on those contributions?"
                    ),
                    purpose=(
                        "让观察到的证据决定下一步诊断方向。"
                        if is_chinese(response_language)
                        else "Let observed evidence determine the next diagnostic direction."
                    ),
                ),
            ]
        return AnalysisPlan(
            objective=intent.objective or question,
            steps=steps,
            max_steps=MAX_ANALYSIS_STEPS,
            status="pending",
        )

    def evaluate_analysis(
        self,
        intent: AnalysisIntent,
        plan: AnalysisPlan,
        evidence: list[Evidence],
        response_language: ResponseLanguage = "en",
    ) -> AnalysisEvaluation:
        zh = is_chinese(response_language)
        latest = evidence[-1]
        if latest.row_count == 0:
            return AnalysisEvaluation(
                critic=CriticResult(
                    sufficient=False,
                    answered_objective=False,
                    missing_evidence=[
                        "当前分析步骤需要非空查询结果。"
                        if zh
                        else "A non-empty result for the current analytical step."
                    ],
                    limitations=latest.limitations,
                    recommended_next_step=None,
                ),
                decision=NextAnalysisDecision(
                    action="clarify",
                    reason=(
                        "现有数据没有返回足以安全确定下一方向的证据。"
                        if zh
                        else "The available data returned no evidence for a safe next direction."
                    ),
                ),
            )

        if len(evidence) == 1:
            revenue_change = latest.key_values.get("total_revenue_change_pct")
            if (
                intent.analysis_type == "diagnostic"
                and isinstance(revenue_change, int | float)
                and revenue_change >= -1
            ):
                return AnalysisEvaluation(
                    critic=CriticResult(
                        sufficient=True,
                        answered_objective=True,
                        limitations=latest.limitations,
                        recommended_next_step=None,
                    ),
                    decision=NextAnalysisDecision(
                        action="finish",
                        reason=(
                            "现有证据未确认收入出现显著下降。"
                            if zh
                            else "The evidence does not confirm a material revenue decline."
                        ),
                    ),
                )
            next_step = next((step for step in plan.steps if step.status == "pending"), None)
            return AnalysisEvaluation(
                critic=CriticResult(
                    sufficient=False,
                    answered_objective=False,
                    missing_evidence=[
                        "订单量与平均订单金额的相对贡献。"
                        if zh
                        else "The relative contribution of order volume and order value."
                    ],
                    limitations=latest.limitations,
                    recommended_next_step=next_step.question if next_step else None,
                ),
                decision=NextAnalysisDecision(
                    action="continue" if next_step else "finish",
                    next_step=next_step,
                    reason=(
                        "第一个结果确认了变化模式, 但尚未识别其驱动因素。"
                        if next_step and zh
                        else "The first result confirms a pattern but does not identify its driver."
                        if next_step
                        else "已没有可执行的有限后续步骤。"
                        if zh
                        else "No bounded follow-up step remains."
                    ),
                ),
            )

        if len(evidence) == 2:
            order_change = _find_change(latest.key_values, ("order_count", "orders"))
            aov_change = _find_change(
                latest.key_values, ("average_order_value", "aov", "average_revenue")
            )
            target = next((step for step in plan.steps if step.status == "pending"), None)
            step_id = target.id if target else f"step_{len(plan.steps) + 1}"
            if aov_change is not None and (order_change is None or aov_change < order_change - 5):
                next_step = AnalysisStep(
                    id=step_id,
                    question=(
                        "按产品类别比较平均订单金额与收入变化。"
                        if zh
                        else "Compare average order value and revenue changes by product category."
                    ),
                    purpose=(
                        "检验产品结构是否推动平均订单金额下降。"
                        if zh
                        else "Test whether product mix is driving the decline in order value."
                    ),
                )
                reason = (
                    "平均订单金额下降幅度高于订单量, 因此下一步分析产品结构和客单价。"
                    if zh
                    else "Average order value declined more than order volume."
                )
                missing = [
                    "产品类别对平均订单金额下降的贡献。"
                    if zh
                    else "Product-category contribution to the average order value decline."
                ]
            elif order_change is not None and (aov_change is None or order_change < aov_change - 5):
                next_step = AnalysisStep(
                    id=step_id,
                    question=(
                        "按地区和销售渠道比较订单量变化。"
                        if zh
                        else "Compare order volume changes by region and sales channel."
                    ),
                    purpose=(
                        "定位对订单下降贡献最大的需求细分。"
                        if zh
                        else "Locate the demand segments contributing most to the order decline."
                    ),
                )
                reason = (
                    "订单量下降幅度高于平均订单金额, 因此下一步分析地区和销售渠道。"
                    if zh
                    else "Order volume declined more than average order value."
                )
                missing = [
                    "地区或渠道对订单量下降的贡献。"
                    if zh
                    else "Region or channel contribution to the order-volume decline."
                ]
            else:
                next_step = AnalysisStep(
                    id=step_id,
                    question=(
                        "比较最相关业务维度上的收入变化。"
                        if zh
                        else "Compare revenue changes across the most relevant business dimension."
                    ),
                    purpose=(
                        "在量价走势接近时继续识别剩余驱动因素。"
                        if zh
                        else "Resolve the remaining driver after volume and value moved similarly."
                    ),
                )
                reason = (
                    "订单量与平均订单金额尚未指向单一主要驱动因素。"
                    if zh
                    else "Volume and order value do not identify a single dominant driver."
                )
                missing = [
                    "细分维度贡献拆解。" if zh else "A segment-level contribution breakdown."
                ]
            return AnalysisEvaluation(
                critic=CriticResult(
                    sufficient=False,
                    answered_objective=False,
                    missing_evidence=missing,
                    limitations=latest.limitations,
                    recommended_next_step=next_step.question,
                ),
                decision=NextAnalysisDecision(
                    action="continue",
                    next_step=next_step,
                    reason=reason,
                    plan_patch={
                        "replace_step_id": target.id if target else None,
                        "source_evidence_ids": [item.id for item in evidence],
                    },
                ),
            )

        return AnalysisEvaluation(
            critic=CriticResult(
                sufficient=True,
                answered_objective=True,
                limitations=[limitation for item in evidence for limitation in item.limitations][
                    :20
                ],
                recommended_next_step=None,
            ),
            decision=NextAnalysisDecision(
                action="finish",
                reason=(
                    "现有证据验证了变化, 并识别出最强驱动因素。"
                    if zh
                    else "The evidence verifies the change and identifies its strongest driver."
                ),
            ),
        )

    def synthesize_analysis(
        self,
        question: str,
        intent: AnalysisIntent,
        plan: AnalysisPlan,
        evidence: list[Evidence],
        critic: CriticResult | None,
        evidence_insufficient: bool,
        response_language: ResponseLanguage = "en",
    ) -> FinalAnalysis:
        del question, intent, plan
        zh = is_chinese(response_language)
        findings = []
        for item in evidence:
            facts = {
                key: float(value)
                for key, value in item.key_values.items()
                if key.endswith(("_change_pct", "_current", "_previous"))
                and isinstance(value, int | float)
                and not isinstance(value, bool)
            }
            findings.append(
                Finding(
                    statement=item.result_summary,
                    evidence_ids=[item.id],
                    facts=facts,
                )
            )
        second = evidence[1].key_values if len(evidence) > 1 else {}
        order_change = _find_change(second, ("order_count", "orders"))
        aov_change = _find_change(second, ("average_order_value", "aov"))
        if order_change is not None and aov_change is not None:
            driver = (
                "average order value"
                if aov_change < order_change
                else "order volume"
                if order_change < aov_change
                else "both order volume and average order value"
            )
            summary = f"The available evidence identifies {driver} as the stronger observed driver."
            if zh:
                driver = {
                    "average order value": "平均订单金额",
                    "order volume": "订单量",
                    "both order volume and average order value": "订单量与平均订单金额",
                }[driver]
                summary = f"现有证据表明, {driver}是当前观察到的主要驱动因素。"
        elif evidence:
            summary = (
                "本次调查已完成, 结论均有已收集证据支持。"
                if zh
                else "The investigation completed with findings supported by the collected evidence."
            )
        else:
            summary = (
                "本次调查未收集到足够证据, 无法形成有依据的结论。"
                if zh
                else "The investigation did not collect enough evidence for a supported conclusion."
            )
        limitations = list(
            dict.fromkeys(
                [limitation for item in evidence for limitation in item.limitations]
                + (critic.limitations if critic else [])
                + (critic.missing_evidence if critic and evidence_insufficient else [])
            )
        )
        return FinalAnalysis(
            executive_summary=summary,
            key_findings=findings,
            limitations=limitations,
            recommended_actions=[
                "复核最强引用证据所指向的业务维度。"
                if zh
                else "Review the operational dimensions identified by the strongest cited evidence."
            ]
            if evidence
            else [],
            evidence_ids=[item.id for item in evidence],
            evidence_insufficient=evidence_insufficient,
        )

    def select_tables(
        self,
        dataset_id: str,
        question: str,
        table_catalog: dict[str, Any],
        response_language: ResponseLanguage = "en",
    ) -> TableSelection:
        zh = is_chinese(response_language)
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
                reason=(
                    "该请求未明确受支持的分析概念。"
                    if zh
                    else "The request does not identify a supported analytical concept."
                ),
                needs_clarification=True,
                clarification_question=(
                    "你希望分析哪个指标或业务维度?"
                    if zh
                    else "Which metric or business dimension should be analyzed?"
                ),
            )
        if dataset_id != "commerce":
            return TableSelection(
                tables=available[:1],
                reason="已选择单表数据集。" if zh else "Single-table dataset selected.",
            )

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
                reason=(
                    "无法将该请求可靠映射到电商数据表。"
                    if zh
                    else "No Commerce table maps confidently to the request."
                ),
                needs_clarification=True,
                clarification_question=(
                    "你希望分析客户、产品、订单、收入还是退款?"
                    if zh
                    else "Should I analyze customers, products, orders, revenue, or refunds?"
                ),
            )
        return TableSelection(
            tables=selected,
            reason="已选择最小关系路径。" if zh else "Selected the minimum relationship path.",
        )

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
        if "volume" in q and any(term in q for term in ("value", "aov", "average order")):
            return SqlGeneration(
                sql=(
                    "SELECT strftime('%Y-%m', order_date) AS month, COUNT(*) AS order_count, "
                    "ROUND(AVG(revenue), 2) AS average_order_value, "
                    "ROUND(SUM(revenue), 2) AS total_revenue FROM sales "
                    "GROUP BY month ORDER BY month"
                ),
                explanation="Decompose monthly revenue into order count and average order value.",
                selected_columns=["sales.order_date", "sales.revenue"],
            )
        if "average order value" in q and any(term in q for term in ("product", "category")):
            return SqlGeneration(
                sql=(
                    "SELECT category, ROUND(AVG(revenue), 2) AS average_order_value, "
                    "ROUND(SUM(revenue), 2) AS total_revenue FROM sales "
                    "GROUP BY category ORDER BY total_revenue DESC"
                ),
                explanation="Compare order value and revenue by product category.",
                selected_columns=["sales.category", "sales.revenue"],
            )
        if "order volume" in q and any(term in q for term in ("region", "channel")):
            dimension = "region" if "region" in q else "sales_channel"
            return SqlGeneration(
                sql=(
                    f"SELECT {dimension}, COUNT(*) AS order_count FROM sales "
                    f"GROUP BY {dimension} ORDER BY order_count DESC"
                ),
                explanation=f"Compare order volume by {dimension}.",
                selected_columns=[f"sales.{dimension}"],
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
        month_column = next(
            (
                column
                for column in columns
                if column.lower() in {"month", "date", "order_date", "period"}
            ),
            None,
        )
        orders_column = next(
            (
                column
                for column in numeric
                if column.lower() in {"orders", "order_count", "quantity"}
            ),
            None,
        )
        revenue_column = next(
            (
                column
                for column in numeric
                if column.lower() in {"revenue", "sales", "sales_amount", "amount"}
            ),
            numeric[0] if numeric else None,
        )
        if (
            month_column
            and orders_column
            and revenue_column
            and "volume" in q
            and any(term in q for term in ("value", "aov", "average order"))
        ):
            return SqlGeneration(
                sql=(
                    f'SELECT "{month_column}" AS period, SUM("{orders_column}") AS order_count, '
                    f'ROUND(1.0 * SUM("{revenue_column}") / NULLIF(SUM("{orders_column}"), 0), 4) '
                    f'AS average_order_value, SUM("{revenue_column}") AS total_revenue '
                    f'FROM "{table}" GROUP BY "{month_column}" ORDER BY "{month_column}"'
                ),
                explanation="Decompose revenue into order volume and average order value by period.",
                selected_columns=[
                    f"{table}.{month_column}",
                    f"{table}.{orders_column}",
                    f"{table}.{revenue_column}",
                ],
            )
        if (
            month_column
            and revenue_column
            and any(term in q for term in ("monthly", "month", "trend"))
        ):
            return SqlGeneration(
                sql=(
                    f'SELECT "{month_column}" AS period, SUM("{revenue_column}") AS total_revenue '
                    f'FROM "{table}" GROUP BY "{month_column}" ORDER BY "{month_column}"'
                ),
                explanation="Aggregate revenue by period.",
                selected_columns=[f"{table}.{month_column}", f"{table}.{revenue_column}"],
            )
        if "average order value" in q and revenue_column:
            category_column = next(
                (
                    column
                    for column in columns
                    if column.lower() in {"category", "product", "product_category"}
                ),
                None,
            )
            if category_column:
                denominator = (
                    f'NULLIF(SUM("{orders_column}"), 0)' if orders_column else "NULLIF(COUNT(*), 0)"
                )
                return SqlGeneration(
                    sql=(
                        f'SELECT "{category_column}", '
                        f'ROUND(1.0 * SUM("{revenue_column}") / {denominator}, 4) '
                        f'AS average_order_value, SUM("{revenue_column}") AS total_revenue '
                        f'FROM "{table}" GROUP BY "{category_column}" ORDER BY total_revenue DESC'
                    ),
                    explanation="Compare average order value and revenue by product category.",
                    selected_columns=[f"{table}.{category_column}", f"{table}.{revenue_column}"],
                )
        if "order volume" in q and orders_column:
            dimension = next(
                (
                    column
                    for column in columns
                    if column.lower() in {"region", "channel", "sales_channel"}
                ),
                None,
            )
            if dimension:
                return SqlGeneration(
                    sql=(
                        f'SELECT "{dimension}", SUM("{orders_column}") AS order_count '
                        f'FROM "{table}" GROUP BY "{dimension}" ORDER BY order_count DESC'
                    ),
                    explanation="Compare order volume by the requested business dimension.",
                    selected_columns=[f"{table}.{dimension}", f"{table}.{orders_column}"],
                )
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
        response_language: ResponseLanguage = "en",
    ) -> InsightOutput:
        del sql
        zh = is_chinese(response_language)
        if not rows:
            return InsightOutput(
                insight=(
                    "观察: 经过校验的查询没有返回匹配行。限制: 该结果无法支持比较或因果解释。"
                    if zh
                    else "Observation: No rows matched the validated query. Limitation: The result cannot "
                    "support a comparison or causal interpretation."
                )
            )
        first = rows[0]
        visible = ", ".join(f"{key}={first.get(key)}" for key in columns[:3])
        return InsightOutput(
            insight=(
                f"观察: 查询返回 {len(rows)} 行; 排名第一的结果为 {visible}。"
                "谨慎解释: 这反映了当前返回数据切片中最显著的模式。"
                "限制: 该结果仅描述所选数据, 不能证明因果关系。"
                if zh
                else f"Observation: The query returned {len(rows)} row(s); the first ranked result is {visible}. "
                "Cautious interpretation: this highlights the strongest pattern in the returned slice. "
                "Limitation: the result describes the selected data and does not establish causality."
            )
        )


StructuredT = TypeVar("StructuredT", bound=BaseModel)
LOCAL_NON_THINKING_EXTRA_BODY = {
    "chat_template_kwargs": {"enable_thinking": False},
}


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
        resolved_extra_body = dict(extra_body or {})
        if provider_name == "local":
            chat_template_kwargs = dict(resolved_extra_body.get("chat_template_kwargs", {}))
            chat_template_kwargs.update(LOCAL_NON_THINKING_EXTRA_BODY["chat_template_kwargs"])
            resolved_extra_body["chat_template_kwargs"] = chat_template_kwargs
            kwargs["reasoning_effort"] = "none"
        if resolved_extra_body:
            kwargs["extra_body"] = resolved_extra_body
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
                is_local = self.provider_name == "local"
                raise AppError(
                    "local_model_error" if is_local else "llm_invalid_output",
                    (
                        "The local model did not return compatible structured output. "
                        "Check the Model ID and tool-calling support."
                        if is_local
                        else "The model did not return compatible structured output."
                    ),
                    status_code=502,
                ) from (recovery_error or first_error)
            try:
                self.last_used_fallback = True
                return fallback()
            except Exception as fallback_error:
                raise AppError(
                    "llm_invalid_output", "The model returned invalid structured output."
                ) from (fallback_error or first_error)

    def rewrite_question(
        self,
        question: str,
        history: list[dict[str, Any]],
        response_language: ResponseLanguage = "en",
    ) -> QuestionRewrite:
        return self._invoke_structured(
            REWRITE_PROMPT,
            QuestionRewrite,
            {
                "history": json.dumps(history[-12:]),
                "question": question,
                "response_language": response_language,
            },
            lambda: self.fallback.rewrite_question(question, history, response_language),
        )

    def understand_analysis_intent(
        self, question: str, response_language: ResponseLanguage = "en"
    ) -> AnalysisIntent:
        return self._invoke_structured(
            ANALYSIS_INTENT_PROMPT,
            AnalysisIntent,
            {"question": question, "response_language": response_language},
            lambda: self.fallback.understand_analysis_intent(question, response_language),
        )

    def create_analysis_plan(
        self,
        question: str,
        intent: AnalysisIntent,
        response_language: ResponseLanguage = "en",
    ) -> AnalysisPlan:
        return self._invoke_structured(
            ANALYSIS_PLAN_PROMPT,
            AnalysisPlan,
            {
                "objective": intent.objective,
                "analysis_type": intent.analysis_type,
                "metrics": json.dumps(intent.metrics),
                "dimensions": json.dumps(intent.dimensions),
                "question": question,
                "max_steps": MAX_ANALYSIS_STEPS,
                "response_language": response_language,
            },
            lambda: self.fallback.create_analysis_plan(question, intent, response_language),
        )

    def evaluate_analysis(
        self,
        intent: AnalysisIntent,
        plan: AnalysisPlan,
        evidence: list[Evidence],
        response_language: ResponseLanguage = "en",
    ) -> AnalysisEvaluation:
        return self._invoke_structured(
            ANALYSIS_EVALUATION_PROMPT,
            AnalysisEvaluation,
            {
                "objective": intent.objective,
                "plan": json.dumps(plan.model_dump(mode="json")),
                "evidence": json.dumps(
                    [item.model_dump(mode="json") for item in evidence],
                    ensure_ascii=True,
                ),
                "step_count": len(evidence),
                "max_steps": plan.max_steps,
                "response_language": response_language,
            },
            lambda: self.fallback.evaluate_analysis(intent, plan, evidence, response_language),
        )

    def synthesize_analysis(
        self,
        question: str,
        intent: AnalysisIntent,
        plan: AnalysisPlan,
        evidence: list[Evidence],
        critic: CriticResult | None,
        evidence_insufficient: bool,
        response_language: ResponseLanguage = "en",
    ) -> FinalAnalysis:
        evidence_payload = [
            {
                "id": item.id,
                "step_id": item.step_id,
                "question": item.question,
                "result_summary": item.result_summary,
                "key_values": item.key_values,
                "row_count": item.row_count,
                "lineage": item.lineage,
                "limitations": item.limitations,
            }
            for item in evidence
        ]
        return self._invoke_structured(
            FINAL_ANALYSIS_PROMPT,
            FinalAnalysis,
            {
                "question": question,
                "intent": json.dumps(intent.model_dump(mode="json")),
                "plan": json.dumps(plan.model_dump(mode="json")),
                "evidence": json.dumps(evidence_payload, ensure_ascii=True),
                "critic": json.dumps(critic.model_dump(mode="json") if critic else None),
                "evidence_insufficient": evidence_insufficient,
                "response_language": response_language,
            },
            lambda: self.fallback.synthesize_analysis(
                question,
                intent,
                plan,
                evidence,
                critic,
                evidence_insufficient,
                response_language,
            ),
        )

    def select_tables(
        self,
        dataset_id: str,
        question: str,
        table_catalog: dict[str, Any],
        response_language: ResponseLanguage = "en",
    ) -> TableSelection:
        return self._invoke_structured(
            TABLE_SELECTION_PROMPT,
            TableSelection,
            {
                "question": question,
                "table_catalog": json.dumps(table_catalog),
                "response_language": response_language,
            },
            lambda: self.fallback.select_tables(
                dataset_id, question, table_catalog, response_language
            ),
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
        response_language: ResponseLanguage = "en",
    ) -> InsightOutput:
        return self._invoke_structured(
            INSIGHT_PROMPT,
            InsightOutput,
            {
                "question": question,
                "sql": sql,
                "columns": json.dumps(columns),
                "rows": json.dumps(rows[:20]),
                "response_language": response_language,
            },
            lambda: self.fallback.write_insight(question, sql, columns, rows, response_language),
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
        allow_mock_fallback=False,
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
