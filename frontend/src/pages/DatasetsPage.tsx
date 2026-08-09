import { Database, KeyRound, Link2, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { CsvUpload } from "../components/CsvUpload";
import { DataTable } from "../components/DataTable";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useI18n } from "../i18n";
import type { DatasetDetail, DatasetSummary } from "../types";

export function DatasetsPage() {
  const { datasetText, formatNumber, t } = useI18n();
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [selected, setSelected] = useState<DatasetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh(preferredId?: string) {
    const items = await api.datasets();
    setDatasets(items);
    const id = preferredId ?? selected?.id ?? items[0]?.id;
    if (id) setSelected(await api.dataset(id));
    setLoading(false);
  }

  useEffect(() => { void refresh().catch((caught: unknown) => { setError(caught instanceof Error ? caught.message : t("datasets.loadError")); setLoading(false); }); }, []);
  if (loading) return <LoadingState label={t("datasets.loading")} />;
  if (error && !datasets.length) return <ErrorState message={error} onRetry={() => void refresh()} />;

  async function remove() {
    if (!selected || selected.is_builtin) return;
    try { await api.deleteDataset(selected.id); setSelected(null); await refresh(); } catch (caught) { setError(caught instanceof Error ? caught.message : t("datasets.deleteError")); }
  }

  const localizedSelected = selected
    ? datasetText(selected.id, { name: selected.name, description: selected.description, questions: selected.suggested_questions })
    : null;
  const selectedSourceLabel = selected?.is_builtin
    ? t("datasets.source.builtin")
    : selected?.source_type === "excel_upload"
      ? t("datasets.source.uploaded_excel")
      : t("datasets.source.uploaded_csv");

  return (
    <div className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
      <div className="space-y-6">
        <section className="panel overflow-hidden"><div className="border-b border-zinc-200 px-4 py-3"><h2 className="text-sm font-bold text-ink">{t("datasets.registry")}</h2></div><div className="divide-y divide-zinc-100">{datasets.map((dataset) => { const localized = datasetText(dataset.id, { name: dataset.name, description: "", questions: [] }); return <button key={dataset.id} className={`flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-zinc-50 ${selected?.id === dataset.id ? "bg-teal-50" : ""}`} onClick={() => void api.dataset(dataset.id).then(setSelected)}><span className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${dataset.is_builtin ? "bg-blue-50 text-blue-700" : "bg-teal-50 text-teal-700"}`}><Database size={16} /></span><span className="min-w-0"><span className="block truncate text-sm font-semibold text-ink">{localized.name}</span><span className="mt-1 block text-xs text-zinc-500">{dataset.table_count} {t("common.tables")} · {formatNumber(dataset.row_count)} {t("common.rows")}</span></span></button>; })}</div></section>
        <section className="panel p-4"><h2 className="mb-3 text-sm font-bold text-ink">{t("datasets.uploadCsv")}</h2><CsvUpload onUploaded={(dataset) => { setSelected(dataset); void refresh(dataset.id); }} /></section>
      </div>
      <section className="panel min-w-0 p-5 lg:p-6">
        {selected ? <div className="space-y-6">
          <div className="flex flex-wrap items-start gap-4 border-b border-zinc-200 pb-5"><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><h2 className="text-lg font-bold text-ink">{localizedSelected?.name}</h2><span className="rounded bg-zinc-100 px-2 py-1 text-xs font-semibold text-zinc-600">{selectedSourceLabel}</span></div><p className="mt-2 text-sm text-zinc-600">{localizedSelected?.description}</p>{selected.source_filename ? <p className="mt-2 text-xs text-zinc-500">{t("datasets.sourceFile")}: {selected.source_filename}</p> : null}{selected.sheet_name ? <p className="mt-1 text-xs text-zinc-500">{t("datasets.sheetName")}: {selected.sheet_name}</p> : null}</div>{!selected.is_builtin ? <button className="secondary-button border-red-200 text-red-700 hover:bg-red-50" onClick={() => void remove()}><Trash2 size={16} /> {t("common.delete")}</button> : null}</div>
          <div className="grid gap-5 md:grid-cols-2">{Object.entries(selected.schema).map(([table, schema]) => <div key={table} className="border border-zinc-200 p-4" style={{ borderRadius: 6 }}><div className="flex items-center justify-between"><h3 className="text-sm font-bold text-ink">{table}</h3><span className="text-xs text-zinc-500">{schema.columns.length} {t("common.columns")}</span></div><div className="mt-3 divide-y divide-zinc-100">{schema.columns.map((column) => <div key={column.name} className="flex items-center gap-2 py-2 text-xs"><span className="min-w-0 flex-1 truncate font-medium text-zinc-700">{column.name}</span>{column.primary_key ? <KeyRound size={13} className="text-amber-600" /> : null}{column.sensitive ? <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700">{t("common.sensitive")}</span> : null}<span className="text-zinc-400">{column.type}</span></div>)}</div>{schema.foreign_keys.length ? <div className="mt-3 border-t border-zinc-100 pt-3">{schema.foreign_keys.map((key) => <div key={`${key.from_column}-${key.to_table}`} className="flex items-center gap-2 text-xs text-blue-700"><Link2 size={13} /> {key.from_column} → {key.to_table}.{key.to_column}</div>)}</div> : null}</div>)}</div>
          {selected.column_mapping.length ? <section><h3 className="label mb-3">{t("datasets.columnMapping")}</h3><DataTable columns={["original", "sanitized"]} rows={selected.column_mapping} /></section> : null}
          <section><h3 className="label mb-3">{t("datasets.preview")}</h3><DataTable columns={selected.preview[0] ? Object.keys(selected.preview[0]) : []} rows={selected.preview} /></section>
          <section><h3 className="label mb-3">{t("datasets.suggestedQuestions")}</h3><div className="flex flex-wrap gap-2">{localizedSelected?.questions.map((question) => <span key={question} className="rounded border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-700">{question}</span>)}</div></section>
        </div> : <div className="flex min-h-80 items-center justify-center text-sm text-zinc-500">{t("datasets.select")}</div>}
      </section>
    </div>
  );
}
