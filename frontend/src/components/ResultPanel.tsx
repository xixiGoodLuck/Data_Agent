import { CheckCircle2, CircleSlash2, Clock3, Rows3 } from "lucide-react";

import type { QueryResponse } from "../types";
import { ApprovalCard } from "./ApprovalCard";
import { DataTable } from "./DataTable";
import { DynamicChart } from "./DynamicChart";
import { LineagePanel } from "./LineagePanel";
import { SqlBlock } from "./SqlBlock";

export function ResultPanel({
  result,
  onApproval,
  approvalBusy,
}: {
  result: QueryResponse;
  onApproval?: (approved: boolean, note: string) => void;
  approvalBusy?: boolean;
}) {
  if (result.status === "pending_approval" && result.approval) {
    return <ApprovalCard approval={result.approval} onDecision={onApproval} busy={approvalBusy} />;
  }
  if (result.status === "needs_clarification") {
    return <div className="border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900" style={{ borderRadius: 8 }}>{result.clarification_question}</div>;
  }
  if (["blocked", "failed", "rejected"].includes(result.status)) {
    return <div className="border border-red-200 bg-red-50 p-4" style={{ borderRadius: 8 }}><div className="flex items-center gap-2 font-semibold text-red-900"><CircleSlash2 size={18} /> {result.status.replaceAll("_", " ")}</div><p className="mt-2 text-sm text-red-800">{result.error?.message ?? result.safety_reason ?? "The query did not complete."}</p>{result.sql ? <div className="mt-4"><SqlBlock sql={result.sql} /></div> : null}</div>;
  }
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3 border-b border-zinc-200 pb-4 text-sm">
        <span className="flex items-center gap-2 font-semibold text-emerald-700"><CheckCircle2 size={17} /> Safe SQL</span>
        <span className="flex items-center gap-2 text-zinc-500"><Rows3 size={16} /> {result.row_count} rows</span>
        <span className="flex items-center gap-2 text-zinc-500"><Clock3 size={16} /> {result.execution_time_ms.toFixed(1)} ms</span>
        <span className="rounded bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-600">{result.risk_level} risk</span>
      </div>
      {result.insight ? <section><h3 className="label mb-2">Grounded insight</h3><p className="text-sm leading-6 text-zinc-700">{result.insight}</p></section> : null}
      {result.chart ? <section><h3 className="label mb-3">Visualization</h3><DynamicChart config={result.chart} columns={result.columns} rows={result.rows} /></section> : <DataTable columns={result.columns} rows={result.rows} />}
      <section><h3 className="label mb-3">Rows</h3><DataTable columns={result.columns} rows={result.rows} /></section>
      {result.sql ? <section><h3 className="label mb-3">Validated SQL</h3><SqlBlock sql={result.sql} /></section> : null}
      {result.lineage ? <section><h3 className="label mb-3">Data lineage</h3><LineagePanel lineage={result.lineage} /></section> : null}
    </div>
  );
}
