import { CheckCircle2, XCircle } from "lucide-react";

import type { EvalRun } from "../types";

const metrics: Array<[keyof EvalRun, string]> = [
  ["result_accuracy", "Result accuracy"],
  ["table_selection_accuracy", "Table selection"],
  ["sql_safety_accuracy", "SQL safety"],
  ["dangerous_sql_block_rate", "Danger block rate"],
  ["approval_accuracy", "Approval accuracy"],
  ["clarification_accuracy", "Clarification"],
  ["chart_selection_accuracy", "Chart selection"],
  ["repair_success_rate", "Repair success"],
];

export function EvalResults({ run, category }: { run: EvalRun; category?: string }) {
  const cases = category ? run.cases.filter((item) => item.category === category) : run.cases;
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map(([key, label]) => <div key={key} className="border-l-2 border-teal-500 bg-zinc-50 px-4 py-3"><div className="text-xs font-medium text-zinc-500">{label}</div><div className="mt-1 text-xl font-bold text-ink">{Number(run[key]).toFixed(1)}%</div></div>)}
      </div>
      <div className="overflow-x-auto border border-zinc-200" style={{ borderRadius: 6 }}>
        <table className="min-w-full text-sm">
          <thead className="bg-zinc-50"><tr className="text-left text-xs text-zinc-500"><th className="px-3 py-3">Case</th><th className="px-3 py-3">Category</th><th className="px-3 py-3">Status</th><th className="px-3 py-3">Expected / actual</th><th className="px-3 py-3 text-right">Latency</th></tr></thead>
          <tbody className="divide-y divide-zinc-100">
            {cases.map((item) => <tr key={item.id}><td className="px-3 py-3"><div className="flex items-center gap-2">{item.passed ? <CheckCircle2 size={16} className="text-emerald-600" /> : <XCircle size={16} className="text-red-600" />}<span className="font-medium text-ink">{item.case_id}</span></div>{item.failure_reasons.length ? <span className="mt-1 block text-xs text-red-600">{item.failure_reasons.join(", ")}</span> : null}</td><td className="px-3 py-3 text-zinc-600">{item.category}</td><td className="px-3 py-3 text-zinc-600">{item.status}</td><td className="max-w-md px-3 py-3 text-xs text-zinc-500"><div className="truncate">E: {JSON.stringify(item.expected)}</div><div className="truncate">A: {JSON.stringify(item.actual)}</div></td><td className="px-3 py-3 text-right tabular-nums text-zinc-600">{item.latency_ms.toFixed(1)} ms</td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  );
}
