import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "../i18n";
import type { QueryResponse, TraceEvent } from "../types";
import { AnalysisProgress } from "./AnalysisProgress";
import { InvestigativeResult } from "./InvestigativeResult";

vi.mock("./DynamicChart", () => ({
  DynamicChart: ({ config }: { config: { title: string } }) => <div>{config.title}</div>,
}));

const trace: TraceEvent[] = [
  {
    id: "step",
    step_index: 1,
    node_name: "prepare_analysis_step_node",
    event_type: "analysis_step_started",
    status: "completed",
    output_summary: JSON.stringify({ question: "Compare monthly revenue." }),
    latency_ms: 1,
  },
  {
    id: "evidence",
    step_index: 2,
    node_name: "create_evidence_node",
    event_type: "evidence_created",
    status: "completed",
    output_summary: JSON.stringify({ result_summary: "Revenue changed by -20%." }),
    latency_ms: 1,
  },
  {
    id: "decision",
    step_index: 3,
    node_name: "evaluate_analysis_node",
    event_type: "analysis_decision",
    status: "continue",
    output_summary: JSON.stringify({ reason: "AOV declined more than order volume." }),
    latency_ms: 1,
  },
];

const result: QueryResponse = {
  request_id: "request-1",
  conversation_id: "conversation-1",
  query_log_id: "log-1",
  status: "success",
    question: "Why did revenue decline?",
    response_language: "en",
  rewritten_question: null,
  analysis_mode: "investigative_analysis",
  analysis_intent: {
    objective: "Find the revenue decline driver.",
    analysis_type: "diagnostic",
    metrics: ["revenue"], dimensions: [], filters: [], time_range: null,
    comparison: "period over period", desired_grain: "month", needs_multi_step: true,
    reason: "Evidence-guided diagnosis.",
  },
  analysis_plan: {
    objective: "Find the revenue decline driver.", max_steps: 3, status: "completed",
    steps: [
      { id: "step_1", question: "Compare monthly revenue.", purpose: "Verify decline.", status: "completed" },
      { id: "step_2", question: "Compare orders and AOV.", purpose: "Find driver.", status: "completed" },
      { id: "step_3", question: "Analyze product categories.", purpose: "Drill down.", status: "skipped" },
    ],
  },
  evidence: [{
    id: "evidence-1", step_id: "step_1", question: "Compare monthly revenue.",
    sql: "SELECT month, SUM(revenue) FROM sales GROUP BY month",
    result_shape: "time_series", result_summary: "Revenue changed by -20%.",
    key_values: { revenue_change_pct: -20 }, row_count: 2, returned_row_count: 2,
    is_truncated: false, lineage: { tables: ["sales"], columns: ["revenue"], schema_hash: "hash" },
    limitations: ["Marketing data is not available."], created_at: "2026-08-10T00:00:00Z",
  }],
  critic_result: { sufficient: true, answered_objective: true, missing_evidence: [], conflicts: [], limitations: [], recommended_next_step: null },
  analysis_step_count: 1,
  evidence_insufficient: false,
  final_analysis: {
    executive_summary: "Revenue declined in the observed period.",
    key_findings: [{ statement: "Revenue changed by -20%.", evidence_ids: ["evidence-1"], facts: { revenue_change_pct: -20 } }],
    limitations: ["Marketing data is not available."],
    recommended_actions: ["Review product pricing."], evidence_ids: ["evidence-1"], evidence_insufficient: false,
  },
  supporting_charts: [{
    evidence_ids: ["evidence-1"], columns: ["metric", "change_pct"],
    rows: [{ metric: "revenue", change_pct: -20 }],
    config: { type: "bar", x_column: "metric", y_columns: ["change_pct"], title: "Revenue change", value_format: "percent" },
  }],
  clarification_question: null, selected_tables: ["sales"], selected_columns: ["sales.revenue"],
  sql: "SELECT 1", safe_sql: true, safety_reason: null, risk_level: "low", approval: null,
  columns: ["employee_name"], rows: [{ employee_name: "Sensitive Person" }], row_count: 1,
  returned_row_count: 1, is_truncated: false,
  chart: null, insight: "Revenue declined.", lineage: null, execution_time_ms: 10,
  trace, used_fallback: false, error: null,
};

describe("InvestigativeResult", () => {
  afterEach(() => { cleanup(); localStorage.clear(); });

  it("shows plan, evidence, decisions, final analysis, limitations, actions, and charts without raw rows", () => {
    localStorage.setItem("insightops-language", "en");
    render(<I18nProvider><InvestigativeResult result={result} /></I18nProvider>);
    expect(screen.getByText("Analyze product categories.")).toBeInTheDocument();
    expect(screen.getByText("Evidence #1")).toBeInTheDocument();
    expect(screen.getAllByText("AOV declined more than order volume.").length).toBeGreaterThan(0);
    expect(screen.getByText("Revenue declined in the observed period.")).toBeInTheDocument();
    expect(screen.getAllByText(/Marketing data is not available/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Review product pricing/)).toBeInTheDocument();
    expect(screen.getByText("Supporting charts")).toBeInTheDocument();
    expect(screen.queryByText("Sensitive Person")).not.toBeInTheDocument();
  });

  it("shows clarification as a request for information", () => {
    render(<I18nProvider><InvestigativeResult result={{ ...result, status: "needs_clarification", clarification_question: "Which period should be compared?", final_analysis: null }} /></I18nProvider>);
    expect(screen.getByText("Which period should be compared?")).toBeInTheDocument();
  });

  it("keeps prior evidence visible while an investigative step awaits approval", () => {
    render(<I18nProvider><InvestigativeResult result={{
      ...result,
      status: "pending_approval",
      final_analysis: null,
      supporting_charts: [],
      approval: { id: "approval-1", risk_level: "high", reasons: ["Sensitive columns"], sql_preview: "SELECT salary FROM employees" },
    }} /></I18nProvider>);
    expect(screen.getByText("Evidence #1")).toBeInTheDocument();
    expect(screen.getByText("Sensitive query approval")).toBeInTheDocument();
  });
});

describe("AnalysisProgress", () => {
  it("renders incremental structured evidence and decision events", () => {
    render(<I18nProvider><AnalysisProgress events={trace.slice(0, 2)} live /></I18nProvider>);
    expect(screen.getByText("Compare monthly revenue.")).toBeInTheDocument();
    expect(screen.getByText("Revenue changed by -20%.")).toBeInTheDocument();
    expect(screen.queryByText("AOV declined more than order volume.")).not.toBeInTheDocument();
  });
});
