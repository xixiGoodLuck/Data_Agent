from __future__ import annotations

import re

from app.core.errors import AppError
from app.schemas.query import Evidence, FinalAnalysis, SupportingChart

_NUMBER = re.compile(r"(?<![\w#])-?\d+(?:\.\d+)?%?")
_UNSUPPORTED_CONCEPTS = {
    "marketing": ("marketing", "advertising", "ad spend", "营销", "广告", "投放"),
    "competition": ("competition", "competitor", "竞争", "竞品"),
    "macro": ("macroeconomic", "economy", "inflation", "宏观", "经济", "通胀"),
    "seasonality": ("seasonality", "seasonal", "季节性", "季节"),
}
_ASSERTIVE_ACTIONS = ("caused", "proves", "demonstrates that", "导致了", "证明", "表明")
_CAUSAL_MARKERS = ("caused", "due to", "driver", "because", "导致", "因为", "驱动")


def _numeric_values(evidence: Evidence) -> list[float]:
    values = [float(evidence.row_count)]
    values.extend(
        float(value)
        for value in evidence.key_values.values()
        if isinstance(value, int | float) and not isinstance(value, bool)
    )
    return values


def _matches(value: float, candidates: list[float]) -> bool:
    return any(
        abs(value - candidate) <= max(0.01, abs(candidate) * 0.0001) for candidate in candidates
    )


def validate_final_analysis(
    analysis: FinalAnalysis,
    evidence: list[Evidence],
    *,
    evidence_insufficient: bool,
) -> FinalAnalysis:
    by_id = {item.id: item for item in evidence}
    referenced = set(analysis.evidence_ids)
    for finding in analysis.key_findings:
        referenced.update(finding.evidence_ids)
    missing = referenced - by_id.keys()
    if missing:
        raise AppError(
            "final_analysis_grounding_error",
            "Final analysis referenced evidence that does not exist.",
        )
    if evidence_insufficient and not analysis.evidence_insufficient:
        raise AppError(
            "final_analysis_grounding_error",
            "Final analysis cannot clear the evidence-insufficient state.",
        )

    corpus = " ".join(
        part
        for item in evidence
        for part in [item.result_summary, *item.limitations, *map(str, item.key_values.keys())]
    ).lower()

    def validate_text(text: str, allowed_numbers: list[float]) -> None:
        for token in _NUMBER.findall(text):
            value = float(token.rstrip("%"))
            if not _matches(value, allowed_numbers):
                raise AppError(
                    "final_analysis_grounding_error",
                    "A numeric finding is not present in its cited evidence.",
                )
        lowered = text.lower()
        for terms in _UNSUPPORTED_CONCEPTS.values():
            if (
                any(term in lowered for term in terms)
                and any(marker in lowered for marker in _CAUSAL_MARKERS)
                and not any(term in corpus for term in terms)
            ):
                raise AppError(
                    "final_analysis_grounding_error",
                    "A causal finding uses a factor that is absent from the evidence.",
                )

    validate_text(
        analysis.executive_summary,
        [value for item in evidence for value in _numeric_values(item)],
    )
    for finding in analysis.key_findings:
        cited = [by_id[item_id] for item_id in finding.evidence_ids]
        allowed_numbers = [value for item in cited for value in _numeric_values(item)]
        for fact_name, fact_value in finding.facts.items():
            if not any(
                fact_name in item.key_values
                and _matches(float(fact_value), [float(item.key_values[fact_name])])
                for item in cited
                if isinstance(item.key_values.get(fact_name), int | float)
            ):
                raise AppError(
                    "final_analysis_grounding_error",
                    "A structured finding fact is not present in its cited evidence.",
                )
        validate_text(finding.statement, allowed_numbers)

    if any(
        term in action.lower()
        for action in analysis.recommended_actions
        for term in _ASSERTIVE_ACTIONS
    ):
        raise AppError(
            "final_analysis_grounding_error",
            "Recommended actions must not be written as verified findings.",
        )
    return analysis


def select_supporting_charts(
    evidence: list[Evidence], evidence_ids: list[str]
) -> list[SupportingChart]:
    selected: list[SupportingChart] = []
    for item in evidence:
        if item.id not in evidence_ids:
            continue
        facts = [
            (key, float(value))
            for key, value in item.key_values.items()
            if key.endswith("_change_pct")
            and isinstance(value, int | float)
            and not isinstance(value, bool)
        ]
        if not facts:
            continue
        selected.append(
            SupportingChart(
                evidence_ids=[item.id],
                config={
                    "type": "bar",
                    "x_column": "metric",
                    "y_columns": ["change_pct"],
                    "series_name": "Change",
                    "title": item.question,
                    "value_format": "percent",
                },
                columns=["metric", "change_pct"],
                rows=[
                    {"metric": key.removesuffix("_change_pct"), "change_pct": value}
                    for key, value in facts[:6]
                ],
            )
        )
        if len(selected) == 3:
            break
    return selected
