import { MessagesSquare, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ConversationSidebar } from "../components/ConversationSidebar";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useConversation } from "../hooks/useConversation";
import { useI18n } from "../i18n";

export function ConversationsPage() {
  const { datasetText, formatDate, t } = useI18n();
  const conversations = useConversation();
  const initialSelection = useRef(false);
  const [pageError, setPageError] = useState<string | null>(null);

  useEffect(() => {
    if (conversations.loading || initialSelection.current) return;
    initialSelection.current = true;
    if (conversations.conversations[0]) {
      void conversations.select(conversations.conversations[0].id);
    }
  }, [conversations.loading, conversations.conversations]);

  async function remove(id: string) {
    if (!window.confirm(t("conversations.deleteConfirm"))) return;
    try {
      setPageError(null);
      await conversations.deleteConversation(id);
    } catch (caught) {
      setPageError(caught instanceof Error ? caught.message : t("conversations.deleteError"));
    }
  }

  if (conversations.loading) return <LoadingState />;
  if (conversations.error) {
    return <ErrorState message={conversations.error} onRetry={() => void conversations.refresh()} />;
  }

  const active = conversations.active;
  return (
    <section className="panel overflow-hidden">
      {pageError ? <div className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{pageError}</div> : null}
      <div className="grid min-h-[680px] lg:grid-cols-[300px_minmax(0,1fr)]">
        <ConversationSidebar
          conversations={conversations.conversations}
          activeId={active?.id ?? null}
          onSelect={(id) => void conversations.select(id)}
          onNew={() => conversations.setActive(null)}
          onDelete={(id) => void remove(id)}
          deletingId={conversations.deletingId}
        />
        <div className="p-5 lg:p-8">
          {active ? (
            <div>
              <div className="flex items-start gap-3 border-b border-zinc-200 pb-5">
                <span className="flex h-10 w-10 items-center justify-center rounded-md bg-blue-50 text-blue-700"><MessagesSquare size={20} /></span>
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-lg font-bold text-ink">{active.title}</h2>
                  <p className="mt-1 text-xs text-zinc-500">{datasetText(active.dataset_id, { name: active.dataset_name ?? active.dataset_id, description: "", questions: [] }).name} · {t("common.updated")} {formatDate(active.updated_at)}</p>
                </div>
                <button
                  type="button"
                  className="icon-button text-red-600"
                  title={t("conversations.delete")}
                  aria-label={t("conversations.delete")}
                  disabled={conversations.deletingId === active.id}
                  onClick={(event) => {
                    event.stopPropagation();
                    void remove(active.id);
                  }}
                >
                  <Trash2 size={17} />
                </button>
              </div>
              <div className="mt-6 space-y-4">
                {active.messages.map((message) => <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}><div className={`max-w-3xl px-4 py-3 text-sm leading-6 ${message.role === "user" ? "bg-ink text-white" : "border border-zinc-200 bg-zinc-50 text-zinc-700"}`} style={{ borderRadius: 8 }}>{message.content}<div className="mt-2 text-[11px] text-zinc-400">{formatDate(message.created_at)}</div></div></div>)}
              </div>
            </div>
          ) : <div className="flex min-h-96 items-center justify-center text-sm text-zinc-500">{t("conversations.select")}</div>}
        </div>
      </div>
    </section>
  );
}
