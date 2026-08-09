import { MessageSquarePlus, Trash2 } from "lucide-react";

import { useI18n } from "../i18n";
import type { ConversationSummary } from "../types";

export function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  deletingId,
}: {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete?: (id: string) => void;
  deletingId?: string | null;
}) {
  const { datasetText, t } = useI18n();
  return (
    <aside className="flex h-[300px] min-h-0 min-w-0 flex-col border-r border-zinc-200 bg-zinc-50 lg:h-full lg:min-h-[420px]">
      <div className="flex h-14 items-center justify-between border-b border-zinc-200 px-3">
        <span className="text-sm font-semibold text-ink">{t("conversations.title")}</span>
        <button type="button" className="icon-button" title={t("conversations.new")} aria-label={t("conversations.new")} onClick={onNew}>
          <MessageSquarePlus size={17} />
        </button>
      </div>
      <div className="min-w-0 flex-1 space-y-1 overflow-y-auto p-2">
        {conversations.map((conversation) => (
          <div
            key={conversation.id}
            className={`group flex min-w-0 items-start rounded-md ${
              activeId === conversation.id ? "bg-white shadow-sm" : "hover:bg-white/70"
            }`}
          >
            <button type="button" className="min-w-0 flex-1 px-3 py-2 text-left" onClick={() => onSelect(conversation.id)}>
              <span className="block truncate text-sm font-medium text-ink">{conversation.title}</span>
              <span className="mt-1 block truncate text-xs text-zinc-500">
                {datasetText(conversation.dataset_id, { name: conversation.dataset_name ?? conversation.dataset_id, description: "", questions: [] }).name} · {conversation.message_count}
              </span>
            </button>
            {onDelete ? (
              <button
                type="button"
                className="mt-1 hidden h-8 w-8 items-center justify-center rounded-md text-zinc-400 hover:bg-red-50 hover:text-red-700 group-hover:flex"
                aria-label={t("conversations.deleteNamed", { name: conversation.title })}
                title={t("conversations.delete")}
                disabled={deletingId === conversation.id}
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(conversation.id);
                }}
              >
                <Trash2 size={15} />
              </button>
            ) : null}
          </div>
        ))}
        {!conversations.length ? (
          <p className="px-3 py-8 text-center text-sm text-zinc-500">{t("conversations.empty")}</p>
        ) : null}
      </div>
    </aside>
  );
}
