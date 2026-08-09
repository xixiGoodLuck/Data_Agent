import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { useConversation } from "../hooks/useConversation";
import { useQueryStream } from "../hooks/useQueryStream";
import { I18nProvider } from "../i18n";
import { TemporaryCredentialsProvider } from "../temporaryCredentials";
import type { ConversationDetail, DatasetDetail, QueryResponse, TraceEvent } from "../types";
import { QueryPage } from "./QueryPage";

vi.mock("../hooks/useConversation", () => ({ useConversation: vi.fn() }));
vi.mock("../hooks/useQueryStream", () => ({ useQueryStream: vi.fn() }));

const dataset: DatasetDetail = {
  id: "sales",
  name: "Sales",
  description: "Sales data",
  source_type: "sample",
  source_filename: null,
  sheet_name: null,
  tables: ["sales"],
  table_count: 1,
  column_count: 1,
  row_count: 1,
  is_builtin: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  suggested_questions: ["What is total revenue?"],
  schema: {
    sales: {
      columns: [{ name: "revenue", type: "REAL", nullable: false, primary_key: false }],
      foreign_keys: [],
      sample_rows: [],
    },
  },
  column_mapping: [],
  preview: [],
};

const conversation: ConversationDetail = {
  id: "conversation-1",
  title: "Delete me",
  dataset_id: "sales",
  dataset_name: "Sales",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  message_count: 1,
  messages: [
    {
      id: "message-1",
      role: "user",
      content: "Existing message",
      query_log_id: "log-1",
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
};

describe("QueryPage conversation deletion", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("deletes the active conversation and clears active result and trace state", async () => {
    localStorage.setItem("insightops-language", "en");
    const refresh = vi.fn().mockResolvedValue(undefined);
    const clear = vi.fn();
    vi.mocked(useConversation).mockImplementation(() => {
      const [active, setActive] = useState<ConversationDetail | null>(conversation);
      return {
        conversations: [conversation],
        active,
        loading: false,
        error: null,
        deletingId: null,
        refresh,
        select: vi.fn().mockResolvedValue(undefined),
        deleteConversation: async (id: string) => {
          await api.deleteConversation(id);
          setActive((current) => (current?.id === id ? null : current));
        },
        setActive,
      };
    });
    vi.mocked(useQueryStream).mockImplementation(() => {
      const [trace, setTrace] = useState<TraceEvent[]>([
        {
          id: "event-1",
          step_index: 1,
          node_name: "intake",
          event_type: "node_completed",
          status: "completed",
          latency_ms: 1,
        },
      ]);
      return {
        result: null,
        setResult: vi.fn(),
        trace,
        setTrace,
        status: "done",
        error: null,
        run: vi.fn(),
        cancel: vi.fn(),
        clear: () => {
          clear();
          setTrace([]);
        },
      };
    });
    vi.spyOn(api, "datasets").mockResolvedValue([dataset]);
    vi.spyOn(api, "dataset").mockResolvedValue(dataset);
    const deleteConversation = vi.spyOn(api, "deleteConversation").mockResolvedValue({ status: "deleted" });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(
      <I18nProvider>
        <TemporaryCredentialsProvider>
          <QueryPage />
        </TemporaryCredentialsProvider>
      </I18nProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Delete Delete me" }));

    await waitFor(() => expect(deleteConversation).toHaveBeenCalledWith("conversation-1"));
    expect(window.confirm).toHaveBeenCalledWith(
      "Delete this conversation?\n\nIts messages, query logs, Agent Trace, approvals, and checkpoints will also be deleted.\n\nThis action cannot be undone.",
    );
    expect(clear).toHaveBeenCalled();
    expect(screen.queryByText("Existing message")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Agent Trace" })).not.toBeInTheDocument();
  });

  it("restores the persisted analysis result and trace when reopening a conversation", async () => {
    const restoredResult = {
      query_log_id: "log-restored",
      conversation_id: "conversation-1",
      analysis_mode: "investigative_analysis",
      trace: [{
        id: "restored-event", step_index: 1, node_name: "finalize_node",
        event_type: "run_completed", status: "success", latency_ms: 1,
      }],
    } as unknown as QueryResponse;
    const restoredConversation: ConversationDetail = {
      ...conversation,
      messages: [{
        id: "message-restored", role: "assistant", content: "Restored analysis",
        query_log_id: "log-restored", created_at: "2026-01-01T00:00:00Z", result: restoredResult,
      }],
    };
    const setResult = vi.fn();
    const setTrace = vi.fn();
    vi.mocked(useConversation).mockReturnValue({
      conversations: [restoredConversation], active: restoredConversation, loading: false,
      error: null, deletingId: null, refresh: vi.fn().mockResolvedValue(undefined),
      select: vi.fn().mockResolvedValue(undefined), deleteConversation: vi.fn(), setActive: vi.fn(),
    });
    vi.mocked(useQueryStream).mockReturnValue({
      result: null, setResult, trace: [], setTrace, status: "idle", error: null,
      run: vi.fn(), cancel: vi.fn(), clear: vi.fn(),
    });
    vi.spyOn(api, "datasets").mockResolvedValue([dataset]);
    vi.spyOn(api, "dataset").mockResolvedValue(dataset);

    render(<I18nProvider><TemporaryCredentialsProvider><QueryPage /></TemporaryCredentialsProvider></I18nProvider>);

    await waitFor(() => expect(setResult).toHaveBeenCalledWith(restoredResult));
    expect(setTrace).toHaveBeenCalledWith(restoredResult.trace);
  });
});
