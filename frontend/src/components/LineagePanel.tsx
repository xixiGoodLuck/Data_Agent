import { GitBranch, Table2 } from "lucide-react";

import { useI18n } from "../i18n";
import type { QueryResponse } from "../types";

export function LineagePanel({ lineage }: { lineage: NonNullable<QueryResponse["lineage"]> }) {
  const { t } = useI18n();
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <div className="label mb-2 flex items-center gap-2"><Table2 size={14} /> {t("lineage.tables")}</div>
        <div className="flex flex-wrap gap-2">{lineage.tables.map((table) => <span key={table} className="rounded border border-blue-200 bg-blue-50 px-2 py-1 text-xs font-medium text-blue-800">{table}</span>)}</div>
      </div>
      <div>
        <div className="label mb-2 flex items-center gap-2"><GitBranch size={14} /> {t("lineage.columns")}</div>
        <div className="flex max-h-24 flex-wrap gap-2 overflow-auto">{lineage.columns.map((column) => <span key={column} className="rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs text-zinc-700">{column}</span>)}</div>
      </div>
      <div className="sm:col-span-2 text-xs text-zinc-400">{t("lineage.schema", { hash: lineage.schema_hash?.slice(0, 16) ?? t("common.unavailable") })}</div>
    </div>
  );
}
