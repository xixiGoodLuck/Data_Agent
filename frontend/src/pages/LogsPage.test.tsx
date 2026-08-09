import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { I18nProvider } from "../i18n";
import type { QueryLog } from "../types";
import { LogsPage } from "./LogsPage";

const log: QueryLog = {
  id: "log-1",
  request_id: "request-1",
  conversation_id: "conversation-1",
  dataset_id: "sales",
  dataset_name: "Sales",
  run_mode: "interactive",
  question: "What is total revenue?",
  rewritten_question: null,
  selected_tables: ["sales"],
  selected_columns: ["revenue"],
  generated_sql: "SELECT SUM(revenue) FROM sales",
  normalized_sql: "SELECT SUM(revenue) FROM sales",
  status: "success",
  safe_sql: true,
  safety_reason: null,
  risk_level: "low",
  approval_id: null,
  row_count: 1,
  chart_type: "number",
  execution_time_ms: 1,
  llm_provider: "mock",
  used_fallback: false,
  error_type: null,
  error_message: null,
  lineage: null,
  created_at: "2026-01-01T00:00:00Z",
  completed_at: "2026-01-01T00:00:01Z",
};

describe("LogsPage deletion", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("does not delete when cancelled and removes only the confirmed query log", async () => {
    localStorage.setItem("insightops-language", "en");
    vi.spyOn(api, "logs").mockResolvedValue({ items: [log], total: 1, page: 1, page_size: 100 });
    vi.spyOn(api, "datasets").mockResolvedValue([]);
    const deleteLog = vi.spyOn(api, "deleteLog").mockResolvedValue({ status: "deleted" });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(
      <I18nProvider>
        <LogsPage />
      </I18nProvider>,
    );

    const deleteButton = await screen.findByRole("button", { name: "Delete query log What is total revenue?" });
    fireEvent.click(deleteButton);
    expect(deleteLog).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.click(deleteButton);

    await waitFor(() => expect(deleteLog).toHaveBeenCalledWith("log-1"));
    expect(screen.queryByText("What is total revenue?")).not.toBeInTheDocument();
  });
});
