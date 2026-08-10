from __future__ import annotations

import re

from app.agent.state import DataAnalysisState


def prompt_guard_reason(question: str) -> str | None:
    text = " ".join(question.lower().split())
    injection_patterns = (
        r"\bignore (?:all |the )?(?:previous|prior|system) instructions\b",
        r"\breveal (?:the )?(?:system|developer) prompt\b",
        r"\b(?:bypass|disable|skip) (?:the )?(?:sql )?(?:safety|validation|guard|policy)\b",
        r"\btranslate (?:these|the) instructions into executable sql\b",
    )
    if any(re.search(pattern, text) for pattern in injection_patterns):
        return "The prompt attempts to override system or SQL safety controls."
    if ("--" in text or "/*" in text) and re.search(r"\b(?:select|execute|sql)\b", text):
        return "Raw SQL comments are not accepted in analytical questions."
    command_patterns = (
        r"\bdrop\s+(?:table|database|index|view)\b",
        r"\bdelete\s+from\b",
        r"\bupdate\s+[a-zA-Z_]\w*\s+set\b",
        r"\binsert\s+into\b",
        r"\b(?:alter|truncate|create)\s+(?:table|database|index|view)\b",
        r"\battach\s+(?:database|['\"]|/)\b",
        r"\bpragma\s+[a-zA-Z_]",
        r"\b(?:vacuum|reindex)\b",
        r"\bexecute\s+raw\s+sql\b",
    )
    if any(re.search(pattern, text) for pattern in command_patterns):
        return "The request asks for a database modification or raw database command."
    access_patterns = (
        r"\b(?:read|access|show|query)\s+(?:the )?(?:application|agent|system)\s+logs\b",
        r"\b(?:read|access|open)\s+(?:a |the )?(?:file|filesystem|path)\b",
        r"\b(?:app\.sqlite|checkpoints?\.sqlite|/etc/|c:\\users\\)\b",
    )
    if any(re.search(pattern, text) for pattern in access_patterns):
        return "The request attempts to access application storage or filesystem paths."
    return None


def route_prompt_guard(state: DataAnalysisState) -> str:
    return "blocked" if state.get("status") == "blocked" else "continue"


def route_dataset(state: DataAnalysisState) -> str:
    return "failed" if state.get("status") == "failed" else "continue"


def route_table_selection(state: DataAnalysisState) -> str:
    return "clarify" if state.get("status") == "needs_clarification" else "continue"


def route_analysis_mode(state: DataAnalysisState) -> str:
    return "investigative" if state.get("analysis_mode") == "investigative_analysis" else "simple"


def route_validation(state: DataAnalysisState) -> str:
    if state.get("status") == "repair_needed":
        return "repair"
    return "safe" if state.get("safe_sql") else "blocked"


def route_risk(state: DataAnalysisState) -> str:
    return "approval" if state.get("requires_approval") else "execute"


def route_approval(state: DataAnalysisState) -> str:
    decision = state.get("approval_decision") or {}
    return "approved" if decision.get("approved") else "rejected"


def route_execution(state: DataAnalysisState) -> str:
    outcome = state.get("execution_outcome")
    if outcome == "success":
        return "evidence" if state.get("analysis_mode") == "investigative_analysis" else "success"
    if outcome == "repair":
        return "repair"
    return "failed"


def route_analysis_decision(state: DataAnalysisState) -> str:
    decision = state.get("next_analysis_decision") or {}
    action = decision.get("action")
    if action == "continue":
        return "continue"
    if action == "clarify":
        return "clarify"
    return "finish"
