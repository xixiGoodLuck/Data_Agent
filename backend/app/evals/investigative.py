from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InvestigativeEvalCase:
    id: str
    question: str
    expected_mode: str = "investigative_analysis"
    minimum_evidence: int = 1
    path_terms: tuple[str, ...] = ()
    expects_final_analysis: bool = True
    expects_evidence_insufficient: bool = False
    expects_approval: bool = False
    fixture: str = "sales"


INVESTIGATIVE_EVAL_CASES = (
    InvestigativeEvalCase(
        "aov_driver",
        "Why did revenue decline?",
        minimum_evidence=3,
        path_terms=("average order value", "product category"),
        fixture="aov_csv",
    ),
    InvestigativeEvalCase(
        "order_driver",
        "Why did revenue decline?",
        minimum_evidence=3,
        path_terms=("order volume", "region", "channel"),
        fixture="orders_csv",
    ),
    InvestigativeEvalCase("no_decline", "Why did revenue decline?", fixture="no_decline_csv"),
    InvestigativeEvalCase(
        "insufficient",
        "Why did revenue decline?",
        minimum_evidence=2,
        expects_evidence_insufficient=True,
        fixture="bounded_csv",
    ),
    InvestigativeEvalCase(
        "approval",
        "Why did workforce performance decline?",
        expects_final_analysis=False,
        expects_approval=True,
        fixture="employees",
    ),
    InvestigativeEvalCase(
        "empty_result", "Why did the filtered metric decline?", fixture="empty_csv"
    ),
    InvestigativeEvalCase("chinese_diagnostic", "为什么这个月收入下降?", fixture="sales"),
    InvestigativeEvalCase("xlsx", "为什么最近收入下降?", minimum_evidence=2, fixture="aov_xlsx"),
)


def score_investigative_response(
    case: InvestigativeEvalCase, response: dict[str, Any]
) -> dict[str, bool]:
    plan_text = " ".join(
        str(step.get("question", "")).lower()
        for step in (response.get("analysis_plan") or {}).get("steps", [])
    )
    checks = {
        "analysis_mode": response.get("analysis_mode") == case.expected_mode,
        "evidence": len(response.get("evidence", [])) >= case.minimum_evidence,
        "dynamic_path": all(term in plan_text for term in case.path_terms),
        "final_analysis": bool(response.get("final_analysis")) == case.expects_final_analysis,
        "evidence_insufficient": bool(response.get("evidence_insufficient"))
        == case.expects_evidence_insufficient,
        "approval": (response.get("status") == "pending_approval") == case.expects_approval,
        "max_steps": len(response.get("evidence", [])) <= 5,
        "evidence_unique": len({item.get("id") for item in response.get("evidence", [])})
        == len(response.get("evidence", [])),
        "grounded_findings": _findings_are_grounded(response),
    }
    return checks


def _findings_are_grounded(response: dict[str, Any]) -> bool:
    evidence_ids = {item.get("id") for item in response.get("evidence", [])}
    analysis = response.get("final_analysis") or {}
    return all(
        set(finding.get("evidence_ids", [])).issubset(evidence_ids)
        for finding in analysis.get("key_findings", [])
    )
