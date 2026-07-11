import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "../api/client";
import {
  TemporaryCredentialsProvider,
  useTemporaryCredentials,
} from "../temporaryCredentials";
import type { EvalRun } from "../types";
import { EvalsPage } from "./EvalsPage";

const completedRun: EvalRun = {
  id: "eval-run-1",
  total_cases: 1,
  passed_cases: 1,
  failed_cases: 0,
  query_success_rate: 100,
  result_accuracy: 100,
  table_selection_accuracy: 100,
  sql_safety_accuracy: 100,
  dangerous_sql_block_rate: 100,
  approval_accuracy: 100,
  clarification_accuracy: 100,
  chart_selection_accuracy: 100,
  repair_success_rate: 100,
  fallback_rate: 0,
  average_latency_ms: 12,
  p95_latency_ms: 12,
  created_at: "2026-07-11T00:00:00Z",
  cases: [],
};

function KeyedEvalPage() {
  const { setDeepseekApiKey } = useTemporaryCredentials();
  useEffect(() => setDeepseekApiKey("sk-eval-ui-test"), [setDeepseekApiKey]);
  return <EvalsPage />;
}

function renderPage() {
  return render(
    <TemporaryCredentialsProvider>
      <KeyedEvalPage />
    </TemporaryCredentialsProvider>,
  );
}

describe("EvalsPage streaming run", () => {
  beforeEach(() => {
    window.localStorage.setItem("insightops-language", "en");
    vi.spyOn(api, "latestEval").mockRejectedValue(
      new ApiError("dataset_not_found", "No evaluation has been run yet.", 404),
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("sends the in-memory key and renders the streamed result", async () => {
    const body = [
      "event: progress",
      'data: {"current":1,"completed":0,"total":1,"case_id":"case-1","phase":"case_started"}',
      "",
      "event: case_result",
      'data: {"current":1,"completed":1,"total":1,"case_id":"case-1","phase":"case_completed"}',
      "",
      "event: result",
      `data: ${JSON.stringify(completedRun)}`,
      "",
      "event: done",
      "data: {}",
      "",
      "",
    ].join("\n");
    const stream = vi.spyOn(api, "evalStream").mockResolvedValue(
      new Response(body, { headers: { "Content-Type": "text/event-stream" } }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Run Eval" }));

    await screen.findByText("1/1 cases passed");
    expect(stream).toHaveBeenCalledWith("sk-eval-ui-test", expect.any(AbortSignal));
  });

  it("aborts the request when the user cancels", async () => {
    let capturedSignal: AbortSignal | undefined;
    vi.spyOn(api, "evalStream").mockImplementation((_key, signal) => {
      capturedSignal = signal;
      return new Promise<Response>((_resolve, reject) => {
        signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Run Eval" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel Eval" }));

    await waitFor(() => expect(capturedSignal?.aborted).toBe(true));
  });
});
