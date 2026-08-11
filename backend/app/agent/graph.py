from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import AnalysisNodes
from app.agent.routing import (
    route_analysis_decision,
    route_analysis_mode,
    route_approval,
    route_dataset,
    route_execution,
    route_final_grounding,
    route_prompt_guard,
    route_risk,
    route_table_selection,
    route_validation,
)
from app.agent.state import DataAnalysisState


def build_analysis_graph(nodes: AnalysisNodes, checkpointer: Any) -> Any:
    builder = StateGraph(DataAnalysisState)
    builder.add_node("intake_node", nodes.intake_node)
    builder.add_node("prompt_guard_node", nodes.prompt_guard_node)
    builder.add_node("load_dataset_node", nodes.load_dataset_node)
    builder.add_node("load_conversation_node", nodes.load_conversation_node)
    builder.add_node("rewrite_question_node", nodes.rewrite_question_node)
    builder.add_node("understand_analysis_intent_node", nodes.understand_analysis_intent_node)
    builder.add_node("create_analysis_plan_node", nodes.create_analysis_plan_node)
    builder.add_node("prepare_analysis_step_node", nodes.prepare_analysis_step_node)
    builder.add_node("select_tables_node", nodes.select_tables_node)
    builder.add_node("read_schema_node", nodes.read_schema_node)
    builder.add_node("generate_sql_node", nodes.generate_sql_node)
    builder.add_node("validate_sql_node", nodes.validate_sql_node)
    builder.add_node("assess_risk_node", nodes.assess_risk_node)
    builder.add_node("approval_interrupt_node", nodes.approval_interrupt_node)
    builder.add_node("execute_sql_node", nodes.execute_sql_node)
    builder.add_node("repair_sql_node", nodes.repair_sql_node)
    builder.add_node("create_evidence_node", nodes.create_evidence_node)
    builder.add_node("evaluate_analysis_node", nodes.evaluate_analysis_node)
    builder.add_node("finish_analysis_node", nodes.finish_analysis_node)
    builder.add_node("synthesize_final_analysis_node", nodes.synthesize_final_analysis_node)
    builder.add_node("validate_final_analysis_node", nodes.validate_final_analysis_node)
    builder.add_node("select_supporting_charts_node", nodes.select_supporting_charts_node)
    builder.add_node("plan_chart_node", nodes.plan_chart_node)
    builder.add_node("write_insight_node", nodes.write_insight_node)
    builder.add_node("persist_result_node", nodes.persist_result_node)
    builder.add_node("finalize_node", nodes.finalize_node)

    builder.add_edge(START, "intake_node")
    builder.add_edge("intake_node", "prompt_guard_node")
    builder.add_conditional_edges(
        "prompt_guard_node",
        route_prompt_guard,
        {"blocked": "persist_result_node", "continue": "load_dataset_node"},
    )
    builder.add_conditional_edges(
        "load_dataset_node",
        route_dataset,
        {"failed": "persist_result_node", "continue": "load_conversation_node"},
    )
    builder.add_edge("load_conversation_node", "rewrite_question_node")
    builder.add_edge("rewrite_question_node", "understand_analysis_intent_node")
    builder.add_conditional_edges(
        "understand_analysis_intent_node",
        route_analysis_mode,
        {
            "simple": "select_tables_node",
            "investigative": "create_analysis_plan_node",
        },
    )
    builder.add_edge("create_analysis_plan_node", "prepare_analysis_step_node")
    builder.add_edge("prepare_analysis_step_node", "select_tables_node")
    builder.add_conditional_edges(
        "select_tables_node",
        route_table_selection,
        {"clarify": "persist_result_node", "continue": "read_schema_node"},
    )
    builder.add_edge("read_schema_node", "generate_sql_node")
    builder.add_edge("generate_sql_node", "validate_sql_node")
    builder.add_conditional_edges(
        "validate_sql_node",
        route_validation,
        {
            "blocked": "persist_result_node",
            "repair": "repair_sql_node",
            "safe": "assess_risk_node",
        },
    )
    builder.add_conditional_edges(
        "assess_risk_node",
        route_risk,
        {"execute": "execute_sql_node", "approval": "approval_interrupt_node"},
    )
    builder.add_conditional_edges(
        "approval_interrupt_node",
        route_approval,
        {"approved": "execute_sql_node", "rejected": "persist_result_node"},
    )
    builder.add_conditional_edges(
        "execute_sql_node",
        route_execution,
        {
            "success": "plan_chart_node",
            "evidence": "create_evidence_node",
            "repair": "repair_sql_node",
            "failed": "persist_result_node",
        },
    )
    builder.add_edge("repair_sql_node", "validate_sql_node")
    builder.add_edge("create_evidence_node", "evaluate_analysis_node")
    builder.add_conditional_edges(
        "evaluate_analysis_node",
        route_analysis_decision,
        {
            "continue": "prepare_analysis_step_node",
            "finish": "finish_analysis_node",
            "clarify": "persist_result_node",
        },
    )
    builder.add_edge("finish_analysis_node", "synthesize_final_analysis_node")
    builder.add_edge("synthesize_final_analysis_node", "validate_final_analysis_node")
    builder.add_conditional_edges(
        "validate_final_analysis_node",
        route_final_grounding,
        {"valid": "select_supporting_charts_node", "failed": "persist_result_node"},
    )
    builder.add_edge("select_supporting_charts_node", "persist_result_node")
    builder.add_edge("plan_chart_node", "write_insight_node")
    builder.add_edge("write_insight_node", "persist_result_node")
    builder.add_edge("persist_result_node", "finalize_node")
    builder.add_edge("finalize_node", END)
    return builder.compile(checkpointer=checkpointer)
