import { AlertTriangle, CheckCircle2, CircleSlash2 } from "lucide-react";

import { useI18n } from "../i18n";
import type { QueryResponse } from "../types";
import { AnalysisProgress, eventPayload } from "./AnalysisProgress";
import { ApprovalCard } from "./ApprovalCard";
import { DynamicChart } from "./DynamicChart";
import { SqlBlock } from "./SqlBlock";

export function InvestigativeResult({ result, onApproval, approvalBusy }: {
  result: QueryResponse;
  onApproval?: (approved: boolean, note: string) => void;
  approvalBusy?: boolean;
}) {
  const { t } = useI18n();
  const evidenceNumber = new Map(result.evidence.map((item, index) => [item.id, index + 1]));
  const decisions = result.trace.filter((event) => event.event_type === "analysis_decision").map(eventPayload);
  return <div className="space-y-6">
    <section><h3 className="label mb-2">{t("analysis.goal")}</h3><p className="text-sm leading-6 text-zinc-800">{result.question}</p></section>
    {result.analysis_plan ? <section><h3 className="label mb-3">{t("analysis.plan")}</h3><ol className="space-y-2">{result.analysis_plan.steps.map((step) => <li key={step.id} className="flex gap-2 text-sm text-zinc-700">{step.status === "completed" ? <CheckCircle2 className="shrink-0 text-emerald-600" size={17} /> : step.status === "skipped" ? <CircleSlash2 className="shrink-0 text-zinc-400" size={17} /> : <span className="h-4 w-4 shrink-0 rounded-full border border-zinc-300" />}<span><span className="font-medium">{step.question}</span>{step.status === "skipped" ? <span className="ml-2 text-xs text-zinc-400">{t("analysis.skipped")}</span> : null}</span></li>)}</ol></section> : null}
    <AnalysisProgress events={result.trace} />
    {result.evidence.length ? <section><h3 className="label mb-3">{t("analysis.evidence")}</h3><div className="space-y-3">{result.evidence.map((item, index) => <article key={item.id} className="rounded-md border border-zinc-200 bg-zinc-50 p-4"><div className="text-xs font-bold uppercase tracking-wide text-teal-700">{t("analysis.evidenceNumber", { number: index + 1 })}</div><h4 className="mt-1 text-sm font-semibold text-ink">{item.question}</h4><p className="mt-2 text-sm leading-6 text-zinc-700">{item.result_summary}</p>{Object.keys(item.key_values).length ? <dl className="mt-3 grid gap-2 sm:grid-cols-2">{Object.entries(item.key_values).map(([key, value]) => <div key={key} className="rounded bg-white px-3 py-2"><dt className="break-all text-[11px] text-zinc-500">{key}</dt><dd className="mt-0.5 text-sm font-semibold text-ink">{String(value)}</dd></div>)}</dl> : null}<div className="mt-3 text-xs text-zinc-500">{t("analysis.sourceStep", { step: item.step_id })}</div><details className="mt-3"><summary className="cursor-pointer text-xs font-medium text-zinc-600">{t("analysis.viewSql")}</summary><div className="mt-2"><SqlBlock sql={item.sql} /></div></details></article>)}</div></section> : null}
    {decisions.length ? <section><h3 className="label mb-3">{t("analysis.decisions")}</h3><div className="space-y-2">{decisions.map((decision, index) => <p key={index} className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm leading-6 text-blue-900">{String(decision.reason ?? "")}</p>)}</div></section> : null}
    {result.final_analysis ? <section className="space-y-4"><div><h3 className="label mb-2">{t("analysis.final")}</h3><p className="text-sm font-medium leading-6 text-ink">{result.final_analysis.executive_summary}</p></div><div><h4 className="text-sm font-semibold text-ink">{t("analysis.findings")}</h4><ul className="mt-2 space-y-2">{result.final_analysis.key_findings.map((finding, index) => <li key={index} className="text-sm leading-6 text-zinc-700">• {finding.statement} <span className="text-xs text-teal-700">{finding.evidence_ids.map((id) => t("analysis.evidenceRef", { number: evidenceNumber.get(id) ?? "?" })).join(", ")}</span></li>)}</ul></div>{result.final_analysis.limitations.length ? <div><h4 className="text-sm font-semibold text-ink">{t("analysis.limitations")}</h4><ul className="mt-2 space-y-1 text-sm text-zinc-600">{result.final_analysis.limitations.map((item) => <li key={item}>• {item}</li>)}</ul></div> : null}{result.final_analysis.recommended_actions.length ? <div><h4 className="text-sm font-semibold text-ink">{t("analysis.actions")}</h4><ul className="mt-2 space-y-1 text-sm text-zinc-700">{result.final_analysis.recommended_actions.map((item) => <li key={item}>• {item}</li>)}</ul></div> : null}{result.final_analysis.evidence_insufficient ? <p className="flex items-center gap-2 text-sm text-amber-800"><AlertTriangle size={16} />{t("analysis.insufficient")}</p> : null}</section> : null}
    {result.supporting_charts.length ? <section><h3 className="label mb-3">{t("analysis.supportingCharts")}</h3><div className="space-y-5">{result.supporting_charts.map((chart, index) => <DynamicChart key={index} config={chart.config} columns={chart.columns} rows={chart.rows} />)}</div></section> : null}
    {result.status === "pending_approval" && result.approval ? <ApprovalCard approval={result.approval} onDecision={onApproval} busy={approvalBusy} /> : null}
    {result.status === "needs_clarification" ? <div className="rounded-md border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900"><strong>{t("analysis.needsInfo")}</strong><p className="mt-1">{result.clarification_question}</p></div> : null}
    {["blocked", "failed", "rejected"].includes(result.status) ? <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">{result.error?.message ?? result.safety_reason ?? t("result.incomplete")}</div> : null}
  </div>;
}
