import type { QueryLog } from "../types";

const statusClass: Record<string, string> = {
  success: "bg-emerald-50 text-emerald-700",
  blocked: "bg-red-50 text-red-700",
  failed: "bg-red-50 text-red-700",
  pending_approval: "bg-amber-50 text-amber-700",
  rejected: "bg-zinc-100 text-zinc-700",
  needs_clarification: "bg-blue-50 text-blue-700",
  processing: "bg-blue-50 text-blue-700",
};

export function QueryLogTable({ logs, onSelect }: { logs: QueryLog[]; onSelect?: (log: QueryLog) => void }) {
  if (!logs.length) return <div className="py-12 text-center text-sm text-zinc-500">No query logs match.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead><tr className="border-b border-zinc-200 text-left text-xs text-zinc-500"><th className="px-3 py-3">Status</th><th className="px-3 py-3">Question</th><th className="px-3 py-3">Dataset</th><th className="px-3 py-3">Tables</th><th className="px-3 py-3 text-right">Rows</th><th className="px-3 py-3 text-right">Latency</th><th className="px-3 py-3">Created</th></tr></thead>
        <tbody className="divide-y divide-zinc-100">
          {logs.map((log) => (
            <tr key={log.id} className={onSelect ? "cursor-pointer hover:bg-zinc-50" : ""} onClick={() => onSelect?.(log)}>
              <td className="px-3 py-3"><span className={`whitespace-nowrap rounded px-2 py-1 text-xs font-semibold ${statusClass[log.status] ?? "bg-zinc-100 text-zinc-700"}`}>{log.status.replaceAll("_", " ")}</span></td>
              <td className="max-w-sm px-3 py-3"><span className="block truncate font-medium text-ink" title={log.question}>{log.question}</span><span className="mt-1 block text-xs text-zinc-400">{log.run_mode}</span></td>
              <td className="whitespace-nowrap px-3 py-3 text-zinc-600">{log.dataset_name ?? log.dataset_id}</td>
              <td className="max-w-56 px-3 py-3 text-xs text-zinc-500"><span className="block truncate">{log.selected_tables.join(", ") || "—"}</span></td>
              <td className="px-3 py-3 text-right tabular-nums text-zinc-600">{log.row_count}</td>
              <td className="px-3 py-3 text-right tabular-nums text-zinc-600">{log.execution_time_ms.toFixed(1)} ms</td>
              <td className="whitespace-nowrap px-3 py-3 text-xs text-zinc-500">{new Date(log.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
