export type QueryStatus =
  | "processing"
  | "needs_clarification"
  | "pending_approval"
  | "success"
  | "blocked"
  | "rejected"
  | "failed";

export interface DatasetColumn {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  sensitive?: boolean;
  date_like?: boolean;
}

export interface DatasetTableSchema {
  columns: DatasetColumn[];
  foreign_keys: Array<{
    from_column: string;
    to_table: string;
    to_column: string;
  }>;
  sample_rows: Record<string, unknown>[];
}

export interface DatasetSummary {
  id: string;
  name: string;
  description: string;
  source_type: "sample" | "csv_upload" | "excel_upload";
  source_filename: string | null;
  sheet_name: string | null;
  tables: string[];
  table_count: number;
  column_count: number;
  row_count: number;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
  suggested_questions: string[];
}

export interface DatasetDetail extends DatasetSummary {
  schema: Record<string, DatasetTableSchema>;
  column_mapping: Array<{ original: string; sanitized: string }>;
  preview: Record<string, unknown>[];
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  query_log_id: string | null;
  created_at: string;
  result?: QueryResponse | null;
}

export interface ConversationSummary {
  id: string;
  title: string;
  dataset_id: string;
  dataset_name: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[];
}

export interface TraceEvent {
  id?: string | null;
  step_index: number;
  node_name: string;
  event_type: string;
  status: string;
  input_summary?: string | null;
  output_summary?: string | null;
  latency_ms: number;
  created_at?: string | null;
}

export interface ChartConfig {
  type: "bar" | "line" | "area" | "pie" | "scatter" | "table" | "number";
  x_column?: string | null;
  y_columns: string[];
  series_name?: string | null;
  title: string;
  value_format: "number" | "currency" | "percent";
}

export interface QueryApprovalSummary {
  id: string;
  risk_level: "medium" | "high";
  reasons: string[];
  sql_preview: string;
}

export interface QueryResponse {
  request_id: string;
  conversation_id: string | null;
  query_log_id: string;
  status: QueryStatus;
  question: string;
  response_language: "zh-CN" | "en";
  rewritten_question: string | null;
  analysis_mode: "simple_query" | "investigative_analysis";
  analysis_intent: AnalysisIntent | null;
  analysis_plan: AnalysisPlan | null;
  evidence: Evidence[];
  critic_result: CriticResult | null;
  analysis_step_count: number;
  evidence_insufficient: boolean;
  final_analysis: FinalAnalysis | null;
  supporting_charts: SupportingChart[];
  clarification_question: string | null;
  selected_tables: string[];
  selected_columns: string[];
  sql: string | null;
  safe_sql: boolean;
  safety_reason: string | null;
  risk_level: "low" | "medium" | "high";
  approval: QueryApprovalSummary | null;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  returned_row_count: number;
  is_truncated: boolean;
  chart: ChartConfig | null;
  insight: string | null;
  lineage: { tables: string[]; columns: string[]; schema_hash: string | null } | null;
  execution_time_ms: number;
  trace: TraceEvent[];
  used_fallback: boolean;
  error: { type: string; message: string; repairable?: boolean } | null;
}

export type AnalysisType =
  | "lookup"
  | "comparison"
  | "ranking"
  | "trend"
  | "diagnostic"
  | "exploratory";

export interface AnalysisIntent {
  objective: string;
  analysis_type: AnalysisType;
  metrics: string[];
  dimensions: string[];
  filters: string[];
  time_range: string | null;
  comparison: string | null;
  desired_grain: string | null;
  needs_multi_step: boolean;
  reason: string;
}

export interface AnalysisStep {
  id: string;
  question: string;
  purpose: string;
  status: "pending" | "running" | "completed" | "skipped";
}

export interface AnalysisPlan {
  objective: string;
  steps: AnalysisStep[];
  max_steps: number;
  status: "pending" | "running" | "completed";
}

export interface Evidence {
  id: string;
  step_id: string;
  question: string;
  sql: string;
  result_shape: "scalar" | "ranking" | "categorical_breakdown" | "time_series" | "period_comparison";
  result_shape_metadata?: {
    shape: Evidence["result_shape"];
    time_column: string | null;
    dimension_columns: string[];
    metric_columns: string[];
    series_columns: string[];
  } | null;
  result_summary: string;
  key_values: Record<string, unknown>;
  series_changes?: Record<string, Record<string, number>>;
  facts?: Array<{
    fact_id: string;
    metric: string;
    dimension: string | null;
    dimension_value: string | null;
    statistic: string;
    value: string | number | boolean;
    unit: string | null;
  }>;
  row_count: number;
  returned_row_count: number;
  is_truncated: boolean;
  lineage: QueryResponse["lineage"];
  limitations: string[];
  created_at: string;
}

export interface CriticResult {
  sufficient: boolean;
  answered_objective: boolean;
  missing_evidence: string[];
  conflicts: string[];
  limitations: string[];
  recommended_next_step: string | null;
}

export interface Finding {
  statement: string;
  evidence_ids: string[];
  fact_ids?: string[];
  facts: Record<string, number>;
}

export interface FinalAnalysis {
  executive_summary: string;
  key_findings: Finding[];
  limitations: string[];
  recommended_actions: string[];
  evidence_ids: string[];
  evidence_insufficient: boolean;
}

export interface SupportingChart {
  evidence_ids: string[];
  config: ChartConfig;
  columns: string[];
  rows: Record<string, unknown>[];
}

export interface LocalModelConfig {
  enabled: boolean;
  base_url: string;
  model: string;
}

export interface QueryRequest {
  dataset_id: string;
  conversation_id?: string | null;
  question: string;
  request_id?: string;
  local_model?: LocalModelConfig;
}

export interface ApprovalRequest {
  id: string;
  query_log_id: string;
  thread_id: string;
  question: string | null;
  risk_level: "medium" | "high";
  reasons: string[];
  sql_preview: string;
  selected_tables: string[];
  selected_columns: string[];
  status: "pending" | "approved" | "rejected" | "expired";
  decision_note: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface QueryLog {
  id: string;
  request_id: string;
  conversation_id: string | null;
  dataset_id: string;
  dataset_name: string | null;
  run_mode: "interactive" | "eval" | "test";
  question: string;
  rewritten_question: string | null;
  selected_tables: string[];
  selected_columns: string[];
  generated_sql: string | null;
  normalized_sql: string | null;
  status: QueryStatus;
  safe_sql: boolean;
  safety_reason: string | null;
  risk_level: "low" | "medium" | "high";
  approval_id: string | null;
  row_count: number;
  chart_type: string | null;
  execution_time_ms: number;
  llm_provider: string;
  used_fallback: boolean;
  error_type: string | null;
  error_message: string | null;
  lineage: QueryResponse["lineage"];
  created_at: string;
  completed_at: string | null;
  result?: QueryResponse | null;
}

export interface PaginatedLogs {
  items: QueryLog[];
  total: number;
  page: number;
  page_size: number;
}

export interface StatsOverview {
  total_queries: number;
  success_count: number;
  success_rate: number;
  blocked_count: number;
  pending_approval_count: number;
  failed_count: number;
  fallback_rate: number;
  average_latency_ms: number;
  p95_latency_ms: number;
  chart_breakdown: Array<{ type: string; count: number }>;
  top_datasets: Array<{ dataset_id: string; name: string | null; count: number }>;
  recent_queries: QueryLog[];
  recent_failures: QueryLog[];
}

export interface EvalCaseResult {
  id: string;
  case_id: string;
  category: string;
  passed: boolean;
  status: string;
  generated_sql: string | null;
  actual_tables: string[];
  actual_chart_type: string | null;
  expected: Record<string, unknown>;
  actual: Record<string, unknown>;
  failure_reasons: string[];
  latency_ms: number;
}

export interface EvalRun {
  id: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  query_success_rate: number;
  result_accuracy: number;
  table_selection_accuracy: number;
  sql_safety_accuracy: number;
  dangerous_sql_block_rate: number;
  approval_accuracy: number;
  clarification_accuracy: number;
  chart_selection_accuracy: number;
  repair_success_rate: number;
  fallback_rate: number;
  average_latency_ms: number;
  p95_latency_ms: number;
  created_at: string;
  cases: EvalCaseResult[];
}

export interface PublicSettings {
  provider: string;
  mode: "mock" | "real";
  model: string;
  upload_limits: { max_bytes: number; max_rows: number; max_columns: number };
  max_result_rows: number;
  query_timeout_seconds: number;
}
