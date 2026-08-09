import { Filter, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { AgentTrace } from "../components/AgentTrace";
import { ErrorState } from "../components/ErrorState";
import { LineagePanel } from "../components/LineagePanel";
import { LoadingState } from "../components/LoadingState";
import { QueryLogTable } from "../components/QueryLogTable";
import { SqlBlock } from "../components/SqlBlock";
import { useI18n } from "../i18n";
import type { DatasetSummary, QueryLog, TraceEvent } from "../types";

export function LogsPage() {
  const { datasetText, label, t } = useI18n();
  const [logs, setLogs] = useState<QueryLog[]>([]);
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [selected, setSelected] = useState<QueryLog | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [filters, setFilters] = useState({ dataset_id: "", status: "", run_mode: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  async function load() { const params = new URLSearchParams({ page: "1", page_size: "100" }); Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value); }); const [result, datasetItems] = await Promise.all([api.logs(params), api.datasets()]); setLogs(result.items); setDatasets(datasetItems); setLoading(false); }
  useEffect(() => { void load().catch((caught: unknown) => { setError(caught instanceof Error ? caught.message : t("logs.loadError")); setLoading(false); }); }, [filters.dataset_id, filters.status, filters.run_mode]);
  if (loading && !logs.length) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  async function inspect(log: QueryLog) { const [detail, trace] = await Promise.all([api.log(log.id), api.events(log.id)]); setSelected(detail); setEvents(trace); }
  async function remove(log: QueryLog) {
    if (!window.confirm(t("logs.deleteConfirm"))) return;
    try {
      await api.deleteLog(log.id);
      setLogs((current) => current.filter((item) => item.id !== log.id));
      if (selected?.id === log.id) {
        setSelected(null);
        setEvents([]);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("logs.deleteError"));
    }
  }
  return <div className="space-y-6"><section className="panel p-4"><div className="grid gap-3 md:grid-cols-[auto_1fr_1fr_1fr]"><div className="flex items-center gap-2 text-sm font-semibold text-zinc-600"><Filter size={17} /> {t("logs.filters")}</div><select className="field" value={filters.dataset_id} onChange={(event) => setFilters({ ...filters, dataset_id: event.target.value })}><option value="">{t("logs.allDatasets")}</option>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{datasetText(dataset.id, { name: dataset.name, description: "", questions: [] }).name}</option>)}</select><select className="field" value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="">{t("logs.allStatuses")}</option>{["success", "blocked", "pending_approval", "needs_clarification", "rejected", "failed"].map((status) => <option key={status} value={status}>{label("status", status)}</option>)}</select><select className="field" value={filters.run_mode} onChange={(event) => setFilters({ ...filters, run_mode: event.target.value })}><option value="">{t("logs.allRunModes")}</option>{["interactive", "eval", "test"].map((mode) => <option key={mode} value={mode}>{label("runMode", mode)}</option>)}</select></div></section><section className="panel overflow-hidden"><QueryLogTable logs={logs} onSelect={(log) => void inspect(log)} onDelete={(log) => void remove(log)} /></section>{selected ? <section className="panel p-5 lg:p-6"><div className="mb-5 flex items-start gap-3 border-b border-zinc-200 pb-4"><div className="min-w-0 flex-1"><h2 className="text-base font-bold text-ink">{selected.question}</h2><p className="mt-1 text-xs text-zinc-500">{label("status", selected.status)} · {selected.execution_time_ms.toFixed(1)} ms · {selected.row_count} {t("common.rows")}</p></div><button className="icon-button" aria-label={t("logs.closeDetails")} title={t("logs.closeDetails")} onClick={() => setSelected(null)}><X size={17} /></button></div><div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]"><div className="space-y-5">{selected.normalized_sql || selected.generated_sql ? <SqlBlock sql={selected.normalized_sql ?? selected.generated_sql ?? ""} /> : null}{selected.lineage ? <LineagePanel lineage={selected.lineage} /> : null}{selected.error_message ? <div className="border border-red-200 bg-red-50 p-3 text-sm text-red-800">{selected.error_message}</div> : null}</div><div><h3 className="label mb-4">{t("common.trace")}</h3><AgentTrace events={events} /></div></div></section> : null}</div>;
}
