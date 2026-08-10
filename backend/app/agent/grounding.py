from __future__ import annotations

import re

from app.core.errors import AppError
from app.schemas.query import Evidence, FinalAnalysis, SupportingChart

_NUMBER = re.compile(r"(?<![A-Za-z0-9_#.])-?\d+(?:\.\d+)?%?")
_SQL_DATE_LITERAL = re.compile(r"'\d{4}-\d{2}(?:-\d{2})?'")
_UNSUPPORTED_CONCEPTS = {
    "marketing": ("marketing", "advertising", "ad spend", "营销", "广告", "投放"),
    "competition": ("competition", "competitor", "竞争", "竞品"),
    "macro": ("macroeconomic", "economy", "inflation", "宏观", "经济", "通胀"),
    "seasonality": ("seasonality", "seasonal", "季节性", "季节"),
}
_ASSERTIVE_ACTIONS = ("caused", "proves", "demonstrates that", "导致了", "证明", "表明")
_CAUSAL_MARKERS = ("caused", "due to", "driver", "because", "导致", "因为", "驱动")
_DECLINE_MARKERS = (
    "decline",
    "declined",
    "decrease",
    "decreased",
    "drop",
    "dropped",
    "fell",
    "down",
    "下降",
    "减少",
    "降低",
    "下滑",
    "降幅",
    "微降",
)
_UNCERTAINTY_MARKERS = (
    "cannot",
    "unable",
    "unknown",
    "insufficient",
    "lack",
    "missing",
    "not available",
    "无法",
    "不能",
    "不足",
    "缺少",
    "缺乏",
    "未知",
    "未提供",
)


def _numeric_values(evidence: Evidence) -> list[float]:
    values = [float(evidence.row_count)]
    date_literals = _SQL_DATE_LITERAL.findall(evidence.sql)
    for literal in date_literals:
        values.extend(float(token) for token in re.findall(r"\d+", literal))
    month_indexes = []
    for literal in date_literals:
        year, month = (int(part) for part in literal.strip("'").split("-")[:2])
        month_indexes.append(year * 12 + month)
        values.extend([float(month - 1 or 12), float(month % 12 + 1)])
    values.extend(
        float(abs(right - left))
        for index, left in enumerate(month_indexes)
        for right in month_indexes[index + 1 :]
    )
    for key, value in evidence.key_values.items():
        values.extend(float(token) for token in re.findall(r"\d+(?:\.\d+)?", key))
        if isinstance(value, int | float) and not isinstance(value, bool):
            values.append(float(value))
            if "rate" in key and abs(float(value)) <= 1:
                values.append(float(value) * 100)
        elif isinstance(value, str):
            values.extend(float(token.rstrip("%")) for token in _NUMBER.findall(value))
    return values


def _matches(value: float, candidates: list[float]) -> bool:
    return any(
        abs(value - candidate) <= max(0.01, abs(candidate) * 0.0001) for candidate in candidates
    )


def _matches_derived(value: float, candidates: list[float]) -> bool:
    if _matches(value, candidates):
        return True
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            if _matches(value, [left * right]):
                return True
            if right and _matches(value, [left / right]):
                return True
            if left and _matches(value, [right / left]):
                return True
            if right and _matches(value, [(left - right) / abs(right) * 100]):
                return True
            if left and _matches(value, [(right - left) / abs(left) * 100]):
                return True
    return False


def _matches_text_number(match: re.Match[str], text: str, candidates: list[float]) -> bool:
    token = match.group()
    value = float(token.rstrip("%"))
    if _matches_derived(value, candidates):
        return True
    if token.startswith("-"):
        return False
    context = text[max(0, match.start() - 24) : match.start()].lower()
    return any(marker in context for marker in _DECLINE_MARKERS) and _matches_derived(
        -value, candidates
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
        for match in _NUMBER.finditer(text):
            if not _matches_text_number(match, text, allowed_numbers):
                raise AppError(
                    "final_analysis_grounding_error",
                    "A numeric finding is not present in its cited evidence.",
                )
        lowered = text.lower()
        sentences = re.split(r"[.!?\u3002\uff01\uff1f]", lowered)
        for terms in _UNSUPPORTED_CONCEPTS.values():
            if any(term in corpus for term in terms):
                continue
            for sentence in sentences:
                if (
                    any(term in sentence for term in terms)
                    and any(marker in sentence for marker in _CAUSAL_MARKERS)
                    and not any(marker in sentence for marker in _UNCERTAINTY_MARKERS)
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
                key == fact_name or key.startswith(f"{fact_name}_")
                for item in cited
                for key, value in item.key_values.items()
                if isinstance(value, int | float) and _matches(float(fact_value), [float(value)])
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
