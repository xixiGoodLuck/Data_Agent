import { describe, expect, it } from "vitest";

import type { TraceEvent } from "../types";
import { dedupeTrace } from "./useQueryStream";

describe("trace deduplication", () => {
  it("deduplicates live and final persisted events by id", () => {
    const event: TraceEvent = {
      id: "event-1",
      step_index: 1,
      node_name: "intake_node",
      event_type: "run_started",
      status: "running",
      latency_ms: 0,
    };
    expect(dedupeTrace([event, { ...event }])).toHaveLength(1);
  });

  it("falls back to a stable composite key", () => {
    const event: TraceEvent = {
      step_index: 2,
      node_name: "prompt_guard_node",
      event_type: "node_completed",
      status: "completed",
      latency_ms: 1,
    };
    expect(dedupeTrace([event, { ...event, latency_ms: 2 }])).toHaveLength(1);
  });
});
