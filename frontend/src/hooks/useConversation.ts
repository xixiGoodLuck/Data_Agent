import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { ConversationDetail, ConversationSummary } from "../types";

export function useConversation() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [active, setActive] = useState<ConversationDetail | null>(null);

  const refresh = useCallback(async () => {
    setConversations(await api.conversations());
  }, []);

  const select = useCallback(async (id: string | null) => {
    setActive(id ? await api.conversation(id) : null);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { conversations, active, refresh, select, setActive };
}
