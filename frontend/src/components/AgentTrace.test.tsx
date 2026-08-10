import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { I18nProvider } from "../i18n";
import type { TraceEvent } from "../types";
import { AgentTrace } from "./AgentTrace";

function event(
  step_index: number,
  node_name: string,
  event_type: string,
  status: string,
): TraceEvent {
  return { step_index, node_name, event_type, status, latency_ms: 1 };
}

function renderTrace(events: TraceEvent[], live = true) {
  return render(<I18nProvider><AgentTrace events={events} live={live} /></I18nProvider>);
}

describe("AgentTrace running event normalization", () => {
  afterEach(cleanup);

  it("shows a spinner for an unmatched node start while live", () => {
    renderTrace([event(1, "intake_node", "node_started", "running")]);

    expect(screen.getAllByTestId("trace-event-spinner")).toHaveLength(1);
  });

  it("hides a node start after its completion arrives", () => {
    renderTrace([
      event(1, "intake_node", "node_started", "running"),
      event(2, "intake_node", "node_completed", "completed"),
    ]);

    expect(screen.queryByTestId("trace-event-spinner")).not.toBeInTheDocument();
    expect(screen.queryByText("Node started")).not.toBeInTheDocument();
    expect(screen.getByText("Node completed")).toBeInTheDocument();
  });

  it("pairs repeated runs only until the next start of the same node", () => {
    renderTrace([
      event(1, "execute_sql_node", "node_started", "running"),
      event(2, "execute_sql_node", "node_completed", "completed"),
      event(3, "execute_sql_node", "node_started", "running"),
    ]);

    expect(screen.getAllByTestId("trace-event-spinner")).toHaveLength(1);
    expect(screen.getAllByText("Node started")).toHaveLength(1);
    expect(screen.getByText("Node completed")).toBeInTheDocument();
  });

  it("does not leave a spinner when a node fails", () => {
    renderTrace([
      event(1, "execute_sql_node", "node_started", "running"),
      event(2, "execute_sql_node", "node_failed", "failed"),
    ]);

    expect(screen.queryByTestId("trace-event-spinner")).not.toBeInTheDocument();
    expect(screen.getByTestId("trace-event-failed")).toBeInTheDocument();
  });

  it("removes all running event spinners after the result is complete", () => {
    renderTrace([
      event(1, "intake_node", "node_started", "running"),
      event(2, "intake_node", "node_completed", "completed"),
      event(3, "finalize_node", "node_started", "running"),
      event(4, "finalize_node", "run_completed", "success"),
    ], false);

    expect(screen.queryByTestId("trace-event-spinner")).not.toBeInTheDocument();
    expect(screen.getAllByText(/completed/i)).toHaveLength(2);
  });
});
