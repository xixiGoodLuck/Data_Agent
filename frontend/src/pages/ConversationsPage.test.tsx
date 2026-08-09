import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { I18nProvider } from "../i18n";
import type { ConversationDetail } from "../types";
import { ConversationsPage } from "./ConversationsPage";

const conversation: ConversationDetail = {
  id: "conversation-1",
  title: "Delete me",
  dataset_id: "sales",
  dataset_name: "Sales",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  message_count: 1,
  messages: [{ id: "message-1", role: "user", content: "Question", query_log_id: "log-1", created_at: "2026-01-01T00:00:00Z" }],
};

describe("ConversationsPage deletion", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("cancels without DELETE and removes the conversation immediately after confirmation", async () => {
    localStorage.setItem("insightops-language", "en");
    vi.spyOn(api, "conversations").mockResolvedValue([conversation]);
    vi.spyOn(api, "conversation").mockResolvedValue(conversation);
    const deleteConversation = vi.spyOn(api, "deleteConversation").mockResolvedValue({ status: "deleted" });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<I18nProvider><ConversationsPage /></I18nProvider>);

    const deleteButton = await screen.findByRole("button", { name: "Delete conversation" });
    fireEvent.click(deleteButton);
    expect(deleteConversation).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.click(deleteButton);

    await waitFor(() => expect(deleteConversation).toHaveBeenCalledWith("conversation-1"));
    expect(screen.queryByText("Delete me")).not.toBeInTheDocument();
    expect(screen.getByText("Select a conversation.")).toBeInTheDocument();
  });
});
