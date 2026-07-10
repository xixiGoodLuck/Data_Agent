import { MessageSquarePlus, Trash2 } from "lucide-react";

import type { ConversationSummary } from "../types";

export function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete?: (id: string) => void;
}) {
  return (
    <aside className="flex h-full min-h-[420px] flex-col border-r border-zinc-200 bg-zinc-50">
      <div className="flex h-14 items-center justify-between border-b border-zinc-200 px-3">
        <span className="text-sm font-semibold text-ink">Conversations</span>
        <button className="icon-button" title="New conversation" aria-label="New conversation" onClick={onNew}>
          <MessageSquarePlus size={17} />
        </button>
      </div>
      <div className="flex-1 space-y-1 overflow-y-auto p-2">
        {conversations.map((conversation) => (
          <div
            key={conversation.id}
            className={`group flex items-start rounded-md ${
              activeId === conversation.id ? "bg-white shadow-sm" : "hover:bg-white/70"
            }`}
          >
            <button className="min-w-0 flex-1 px-3 py-2 text-left" onClick={() => onSelect(conversation.id)}>
              <span className="block truncate text-sm font-medium text-ink">{conversation.title}</span>
              <span className="mt-1 block text-xs text-zinc-500">
                {conversation.dataset_name ?? conversation.dataset_id} · {conversation.message_count}
              </span>
            </button>
            {onDelete ? (
              <button
                className="mt-1 hidden h-8 w-8 items-center justify-center rounded-md text-zinc-400 hover:bg-red-50 hover:text-red-700 group-hover:flex"
                aria-label={`Delete ${conversation.title}`}
                title="Delete conversation"
                onClick={() => onDelete(conversation.id)}
              >
                <Trash2 size={15} />
              </button>
            ) : null}
          </div>
        ))}
        {!conversations.length ? (
          <p className="px-3 py-8 text-center text-sm text-zinc-500">No conversations yet.</p>
        ) : null}
      </div>
    </aside>
  );
}
