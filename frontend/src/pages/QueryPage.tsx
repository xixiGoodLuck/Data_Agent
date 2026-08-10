import { Database, MessageSquareText, RotateCcw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import { AgentTrace } from "../components/AgentTrace";
import { AnalysisProgress } from "../components/AnalysisProgress";
import { ConversationSidebar } from "../components/ConversationSidebar";
import { DatasetSelector } from "../components/DatasetSelector";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { QueryInput } from "../components/QueryInput";
import { ResultPanel } from "../components/ResultPanel";
import { useConversation } from "../hooks/useConversation";
import { useQueryStream } from "../hooks/useQueryStream";
import { useI18n } from "../i18n";
import { useTemporaryCredentials } from "../temporaryCredentials";
import type { DatasetDetail, DatasetSummary } from "../types";

export function QueryPage() {
  const { datasetText, t } = useI18n();
  const { deepseekApiKey, localModel } = useTemporaryCredentials();
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [datasetId, setDatasetId] = useState("commerce");
  const [dataset, setDataset] = useState<DatasetDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const conversations = useConversation();
  const stream = useQueryStream();

  useEffect(() => {
    void api.datasets().then((items) => {
      setDatasets(items);
      if (!items.some((item) => item.id === datasetId) && items[0]) setDatasetId(items[0].id);
      setLoading(false);
    }).catch((caught: unknown) => {
      setPageError(caught instanceof Error ? caught.message : t("query.datasetsLoadError"));
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!datasetId) return;
    void api.dataset(datasetId).then(setDataset).catch((caught: unknown) => setPageError(caught instanceof Error ? caught.message : t("query.datasetLoadError")));
  }, [datasetId]);

  useEffect(() => {
    if (!stream.result?.conversation_id) return;
    setPendingQuestion(null);
    void conversations.refresh().then(() => conversations.select(stream.result?.conversation_id ?? null));
  }, [stream.result?.conversation_id]);

  useEffect(() => {
    const restored = [...(conversations.active?.messages ?? [])]
      .reverse()
      .find((message) => message.result)?.result;
    if (!restored) return;
    stream.setResult(restored);
    stream.setTrace(restored.trace);
  }, [conversations.active?.id]);

  const schemaColumns = useMemo(() => dataset ? Object.values(dataset.schema).reduce((sum, table) => sum + table.columns.length, 0) : 0, [dataset]);

  function ask(question: string) {
    setPendingQuestion(question);
    setLastQuestion(question);
    void stream.run({
      dataset_id: datasetId,
      conversation_id: conversations.active?.id ?? null,
      question,
      request_id: crypto.randomUUID(),
    });
  }

  async function decide(approved: boolean, note: string) {
    const id = stream.result?.approval?.id;
    if (!id) return;
    setApprovalBusy(true);
    try {
      const result = await api.decideApproval(id, approved, note, deepseekApiKey, localModel);
      stream.setResult(result);
      stream.setTrace((current) => {
        const seen = new Set<string>();
        return [...current, ...result.trace].filter((event) => {
          const key = event.id ?? `${event.step_index}:${event.node_name}:${event.event_type}`;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
      });
      await conversations.refresh();
      if (result.conversation_id) await conversations.select(result.conversation_id);
    } catch (caught) {
      setPageError(caught instanceof Error ? caught.message : t("query.approvalError"));
    } finally {
      setApprovalBusy(false);
    }
  }

  async function removeConversation(id: string) {
    if (!window.confirm(t("conversations.deleteConfirm"))) return;
    try {
      const deletingActive = conversations.active?.id === id;
      await conversations.deleteConversation(id);
      if (deletingActive) {
        setPendingQuestion(null);
        setLastQuestion(null);
        stream.clear();
      }
    } catch (caught) {
      setPageError(caught instanceof Error ? caught.message : t("conversations.deleteError"));
    }
  }

  async function clearConversations() {
    stream.cancel();
    try {
      await conversations.clearConversations();
      setPendingQuestion(null);
      setLastQuestion(null);
      stream.clear();
      setClearConfirmOpen(false);
    } catch (caught) {
      setPageError(caught instanceof Error ? caught.message : t("conversations.clearError"));
    }
  }

  if (loading) return <LoadingState label={t("query.loading")} />;
  if (pageError && !datasets.length) return <ErrorState message={pageError} />;

  const messages = conversations.active?.messages ?? [];
  const localizedDataset = dataset
    ? datasetText(dataset.id, { name: dataset.name, description: dataset.description, questions: dataset.suggested_questions })
    : null;
  return (
    <div className="space-y-6">
      {pageError ? <div className="border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" style={{ borderRadius: 6 }}>{pageError}</div> : null}
      <section className="panel overflow-hidden">
        <div className="grid min-h-[620px] min-w-0 grid-cols-[minmax(0,1fr)] lg:grid-cols-[240px_minmax(0,1fr)_300px]">
          <ConversationSidebar
            conversations={conversations.conversations}
            activeId={conversations.active?.id ?? null}
            onSelect={(id) => {
              stream.clear();
              void conversations.select(id).then(() => {
                const selected = conversations.conversations.find((item) => item.id === id);
                if (selected) setDatasetId(selected.dataset_id);
              });
            }}
            onNew={() => {
              conversations.setActive(null);
              setPendingQuestion(null);
              setLastQuestion(null);
              stream.clear();
            }}
            onDelete={(id) => void removeConversation(id)}
            onClear={() => setClearConfirmOpen(true)}
            deletingId={conversations.deletingId}
            clearing={conversations.clearing}
          />
          <div className="flex min-h-[500px] min-w-0 flex-col border-b border-zinc-200 lg:border-b-0 lg:border-r">
            <div className="flex-1 space-y-4 overflow-y-auto p-4 lg:p-6">
              {!messages.length && !pendingQuestion ? (
                <div className="flex h-full min-h-72 flex-col items-center justify-center text-center">
                  <span className="flex h-12 w-12 items-center justify-center rounded-md bg-teal-50 text-teal-700"><MessageSquareText size={24} /></span>
                  <h2 className="mt-4 text-base font-bold text-ink">{t("query.askTitle", { dataset: localizedDataset?.name ?? t("query.yourData") })}</h2>
                  <div className="mt-5 flex max-w-xl flex-wrap justify-center gap-2">{localizedDataset?.questions.slice(0, 4).map((question) => <button key={question} className="secondary-button text-left font-medium" onClick={() => ask(question)}>{question}</button>)}</div>
                </div>
              ) : null}
              {messages.map((message) => <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}><div className={`max-w-[82%] break-words px-3 py-2 text-sm leading-6 ${message.role === "user" ? "bg-ink text-white" : "border border-zinc-200 bg-zinc-50 text-zinc-700"}`} style={{ borderRadius: 8 }}>{message.content}</div></div>)}
              {pendingQuestion ? <div className="flex justify-end"><div className="max-w-[82%] break-words bg-ink px-3 py-2 text-sm leading-6 text-white" style={{ borderRadius: 8 }}>{pendingQuestion}</div></div> : null}
              {stream.status === "streaming" ? <div className="flex items-center gap-2 text-sm text-zinc-500"><Sparkles size={16} className="text-teal-600" /> {t("query.agentWorking")}</div> : null}
            </div>
            <QueryInput onSubmit={ask} onCancel={stream.cancel} streaming={stream.status === "streaming"} disabled={!datasetId} />
          </div>
          <aside className="min-w-0 bg-zinc-50 p-4 lg:p-5">
            <DatasetSelector datasets={datasets} value={datasetId} disabled={stream.status === "streaming" || Boolean(conversations.active)} onChange={(value) => { setDatasetId(value); stream.clear(); }} />
            {dataset ? <div className="mt-5 min-w-0 space-y-4"><div className="grid grid-cols-2 gap-2"><div className="bg-white p-3"><div className="text-xs text-zinc-500">{t("query.tables")}</div><div className="mt-1 text-lg font-bold text-ink">{dataset.table_count}</div></div><div className="bg-white p-3"><div className="text-xs text-zinc-500">{t("query.columns")}</div><div className="mt-1 text-lg font-bold text-ink">{schemaColumns}</div></div></div><div><div className="label mb-2 flex items-center gap-2"><Database size={14} /> {t("common.schema")}</div><div className="space-y-3">{Object.entries(dataset.schema).map(([table, schema]) => <div key={table} className="min-w-0"><div className="break-all text-sm font-semibold text-ink">{table}</div><div className="mt-1 flex min-w-0 flex-wrap gap-1">{schema.columns.slice(0, 12).map((column) => <span key={column.name} className={`max-w-full break-all rounded border px-1.5 py-0.5 text-[11px] ${column.sensitive ? "border-amber-200 bg-amber-50 text-amber-800" : "border-zinc-200 bg-white text-zinc-600"}`}>{column.name}</span>)}</div></div>)}</div></div><p className="break-words text-xs leading-5 text-zinc-500">{localizedDataset?.description}</p></div> : null}
          </aside>
        </div>
      </section>
      {clearConfirmOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" role="presentation">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="clear-conversations-title">
            <h2 id="clear-conversations-title" className="text-base font-bold text-ink">{t("conversations.clear")}</h2>
            <p className="mt-3 text-sm leading-6 text-zinc-600">{t("conversations.clearConfirm")}</p>
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" className="secondary-button" disabled={conversations.clearing} onClick={() => setClearConfirmOpen(false)}>{t("conversations.clearCancel")}</button>
              <button type="button" className="rounded-md bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-50" disabled={conversations.clearing} onClick={() => void clearConversations()}>
                {conversations.clearing ? t("conversations.clearing") : t("conversations.clearAction")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {(stream.result || stream.trace.length || stream.error) ? <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="panel p-5 lg:p-6">{stream.error ? <ErrorState message={stream.error} onRetry={lastQuestion ? () => ask(lastQuestion) : undefined} /> : stream.result ? <ResultPanel result={stream.result} onApproval={(approved, note) => void decide(approved, note)} approvalBusy={approvalBusy} /> : stream.trace.length ? <AnalysisProgress events={stream.trace} live={stream.status === "streaming"} /> : <LoadingState label={t("query.waiting")} />}</section>
        <section className="panel self-start p-5"><div className="mb-4 flex items-center justify-between"><h2 className="text-sm font-bold text-ink">{t("query.agentTrace")}</h2>{stream.status === "done" && lastQuestion ? <button className="icon-button" title={t("query.retry")} aria-label={t("query.retry")} onClick={() => ask(lastQuestion)}><RotateCcw size={16} /></button> : null}</div><AgentTrace events={stream.trace} live={stream.status === "streaming"} /></section>
      </div> : null}
    </div>
  );
}
