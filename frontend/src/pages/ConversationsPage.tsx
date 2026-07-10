import { MessagesSquare, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { ConversationSidebar } from "../components/ConversationSidebar";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useI18n } from "../i18n";
import type { ConversationDetail, ConversationSummary } from "../types";

export function ConversationsPage() {
  const { datasetText, formatDate, t } = useI18n();
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [active, setActive] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  async function load() { const conversations = await api.conversations(); setItems(conversations); if (!active && conversations[0]) setActive(await api.conversation(conversations[0].id)); setLoading(false); }
  useEffect(() => { void load().catch((caught: unknown) => { setError(caught instanceof Error ? caught.message : t("conversations.loadError")); setLoading(false); }); }, []);
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  async function remove(id: string) { await api.deleteConversation(id); if (active?.id === id) setActive(null); await load(); }
  return <section className="panel overflow-hidden"><div className="grid min-h-[680px] lg:grid-cols-[300px_minmax(0,1fr)]"><ConversationSidebar conversations={items} activeId={active?.id ?? null} onSelect={(id) => void api.conversation(id).then(setActive)} onNew={() => setActive(null)} onDelete={(id) => void remove(id)} /><div className="p-5 lg:p-8">{active ? <div><div className="flex items-start gap-3 border-b border-zinc-200 pb-5"><span className="flex h-10 w-10 items-center justify-center rounded-md bg-blue-50 text-blue-700"><MessagesSquare size={20} /></span><div className="min-w-0 flex-1"><h2 className="truncate text-lg font-bold text-ink">{active.title}</h2><p className="mt-1 text-xs text-zinc-500">{datasetText(active.dataset_id, { name: active.dataset_name ?? active.dataset_id, description: "", questions: [] }).name} · {t("common.updated")} {formatDate(active.updated_at)}</p></div><button className="icon-button text-red-600" title={t("conversations.delete")} aria-label={t("conversations.delete")} onClick={() => void remove(active.id)}><Trash2 size={17} /></button></div><div className="mt-6 space-y-4">{active.messages.map((message) => <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}><div className={`max-w-3xl px-4 py-3 text-sm leading-6 ${message.role === "user" ? "bg-ink text-white" : "border border-zinc-200 bg-zinc-50 text-zinc-700"}`} style={{ borderRadius: 8 }}>{message.content}<div className={`mt-2 text-[11px] ${message.role === "user" ? "text-zinc-400" : "text-zinc-400"}`}>{formatDate(message.created_at)}</div></div></div>)}</div></div> : <div className="flex min-h-96 items-center justify-center text-sm text-zinc-500">{t("conversations.select")}</div>}</div></div></section>;
}
