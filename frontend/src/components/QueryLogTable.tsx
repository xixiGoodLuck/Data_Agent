import { Trash2 } from "lucide-react";

import { useI18n } from "../i18n";
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

export function QueryLogTable({
  logs,
  onSelect,
  onDelete,
}: {
  logs: QueryLog[];
  onSelect?: (log: QueryLog) => void;
  onDelete?: (log: QueryLog) => void;
}) {
  const { datasetText, formatDate, label, t } = useI18n();
  if (!logs.length) return <div className="py-12 text-center text-sm text-zinc-500">{t("logs.noMatch")}</div>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead><tr className="border-b border-zinc-200 text-left text-xs text-zinc-500"><th className="px-3 py-3">{t("common.status")}</th><th className="px-3 py-3">{t("common.question")}</th><th className="px-3 py-3">{t("logs.dataset")}</th><th className="px-3 py-3">{t("logs.tables")}</th><th className="px-3 py-3 text-right">{t("logs.rows")}</th><th className="px-3 py-3 text-right">{t("common.latency")}</th><th className="px-3 py-3">{t("common.created")}</th>{onDelete ? <th className="w-12 px-3 py-3"><span className="sr-only">{t("logs.delete")}</span></th> : null}</tr></thead>
        <tbody className="divide-y divide-zinc-100">
          {logs.map((log) => (
            <tr key={log.id} className={onSelect ? "cursor-pointer hover:bg-zinc-50" : ""} onClick={() => onSelect?.(log)}>
              <td className="px-3 py-3"><span className={`whitespace-nowrap rounded px-2 py-1 text-xs font-semibold ${statusClass[log.status] ?? "bg-zinc-100 text-zinc-700"}`}>{label("status", log.status)}</span></td>
              <td className="max-w-sm px-3 py-3"><span className="block truncate font-medium text-ink" title={log.question}>{log.question}</span><span className="mt-1 block text-xs text-zinc-400">{label("runMode", log.run_mode)}</span></td>
              <td className="whitespace-nowrap px-3 py-3 text-zinc-600">{datasetText(log.dataset_id, { name: log.dataset_name ?? log.dataset_id, description: "", questions: [] }).name}</td>
              <td className="max-w-56 px-3 py-3 text-xs text-zinc-500"><span className="block truncate">{log.selected_tables.join(", ") || "—"}</span></td>
              <td className="px-3 py-3 text-right tabular-nums text-zinc-600">{log.row_count}</td>
              <td className="px-3 py-3 text-right tabular-nums text-zinc-600">{log.execution_time_ms.toFixed(1)} ms</td>
              <td className="whitespace-nowrap px-3 py-3 text-xs text-zinc-500">{formatDate(log.created_at)}</td>
              {onDelete ? <td className="px-3 py-3"><button className="icon-button text-zinc-400 hover:text-red-700" aria-label={t("logs.deleteNamed", { question: log.question })} title={t("logs.delete")} onClick={(event) => { event.stopPropagation(); onDelete(log); }}><Trash2 size={15} /></button></td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
