import { describe, expect, it } from "vitest";

import { SseParser } from "./sse";

describe("SseParser", () => {
  it("parses events split across arbitrary chunks", () => {
    const parser = new SseParser();
    expect(parser.push("id: 1\nevent: no")).toEqual([]);
    const events = parser.push('de\ndata: {"step_index":1,"node_name":"intake"}\n\n');
    expect(events).toEqual([
      {
        id: "1",
        event: "node",
        data: { step_index: 1, node_name: "intake" },
      },
    ]);
  });

  it("marks malformed JSON without throwing", () => {
    const parser = new SseParser();
    const [event] = parser.push("event: node\ndata: {broken}\n\n");
    expect(event.malformed).toBe(true);
    expect(event.data).toBe("{broken}");
  });

  it("supports CRLF and multiple data lines", () => {
    const parser = new SseParser();
    const [event] = parser.push('event: result\r\ndata: {"ok":\r\ndata: true}\r\n\r\n');
    expect(event.event).toBe("result");
    expect(event.data).toEqual({ ok: true });
  });
});
