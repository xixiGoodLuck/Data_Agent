import { useCallback, useEffect, useRef, useState } from "react";

import { parseQueryResponse } from "../api/client";
import { consumeSseResponse } from "../api/sse";
import { useI18n } from "../i18n";
import type { QueryRequest, QueryResponse, TraceEvent } from "../types";

export function dedupeTrace(events: TraceEvent[]): TraceEvent[] {
  const seen = new Set<string>();
  return events.filter((event) => {
    const key = event.id ?? `${event.step_index}:${event.node_name}:${event.event_type}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function useQueryStream() {
  const { t } = useI18n();
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [status, setStatus] = useState<"idle" | "streaming" | "done" | "cancelled">("idle");
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setStatus((current) => (current === "streaming" ? "cancelled" : current));
  }, []);

  const clear = useCallback(() => {
    cancel();
    setResult(null);
    setTrace([]);
    setError(null);
    setStatus("idle");
  }, [cancel]);

  const run = useCallback(
    async (payload: QueryRequest) => {
      cancel();
      const abortController = new AbortController();
      controller.current = abortController;
      setResult(null);
      setTrace([]);
      setError(null);
      setStatus("streaming");
      try {
        const response = await fetch("/api/query/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: abortController.signal,
        });
        await consumeSseResponse(
          response,
          (message) => {
            if (message.malformed) return;
            if (["run_started", "node", "approval_required"].includes(message.event)) {
              const event = message.data as TraceEvent;
              if (event && typeof event.step_index === "number") {
                setTrace((current) => dedupeTrace([...current, event]));
              }
            }
            if (message.event === "result") {
              const parsed = parseQueryResponse(message.data);
              setResult(parsed);
              setTrace((current) => dedupeTrace([...current, ...parsed.trace]));
            }
            if (message.event === "error") {
              const payloadError = message.data as { message?: string };
              setError(payloadError?.message ?? t("query.streamError"));
            }
            if (message.event === "done") setStatus("done");
          },
          abortController.signal,
        );
        setStatus("done");
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          setStatus("cancelled");
        } else {
          setError(caught instanceof Error ? caught.message : t("query.streamError"));
          setStatus("done");
        }
      } finally {
        if (controller.current === abortController) controller.current = null;
      }
    },
    [cancel, t],
  );

  useEffect(() => cancel, [cancel]);

  return { result, setResult, trace, setTrace, status, error, run, cancel, clear };
}
