import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { ConversationDetail, ConversationSummary } from "../types";

export function useConversation() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [active, setActive] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setConversations(await api.conversations());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Conversations failed to load.");
      throw caught;
    } finally {
      setLoading(false);
    }
  }, []);

  const select = useCallback(async (id: string | null) => {
    setActive(id ? await api.conversation(id) : null);
  }, []);

  const deleteConversation = useCallback(async (id: string) => {
    setDeletingId(id);
    try {
      await api.deleteConversation(id);
      setConversations((current) => current.filter((conversation) => conversation.id !== id));
      setActive((current) => (current?.id === id ? null : current));
    } finally {
      setDeletingId(null);
    }
  }, []);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  return {
    conversations,
    active,
    loading,
    error,
    deletingId,
    refresh,
    select,
    deleteConversation,
    setActive,
  };
}
