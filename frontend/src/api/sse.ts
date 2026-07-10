export interface SseMessage {
  id?: string;
  event: string;
  data: unknown;
  malformed?: boolean;
}

export class SseParser {
  private buffer = "";

  push(chunk: string): SseMessage[] {
    this.buffer = (this.buffer + chunk).replace(/\r\n/g, "\n");
    const messages: SseMessage[] = [];
    let boundary = this.buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const message = this.parseBlock(block);
      if (message) messages.push(message);
      boundary = this.buffer.indexOf("\n\n");
    }
    return messages;
  }

  finish(): SseMessage[] {
    if (!this.buffer.trim()) return [];
    const message = this.parseBlock(this.buffer);
    this.buffer = "";
    return message ? [message] : [];
  }

  private parseBlock(block: string): SseMessage | null {
    if (!block.trim()) return null;
    let event = "message";
    let id: string | undefined;
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue;
      const colon = line.indexOf(":");
      const field = colon >= 0 ? line.slice(0, colon) : line;
      const value = colon >= 0 ? line.slice(colon + 1).replace(/^ /, "") : "";
      if (field === "event") event = value;
      if (field === "id") id = value;
      if (field === "data") dataLines.push(value);
    }
    const raw = dataLines.join("\n");
    try {
      return { id, event, data: raw ? JSON.parse(raw) : null };
    } catch {
      return { id, event, data: raw, malformed: true };
    }
  }
}

export async function consumeSseResponse(
  response: Response,
  onMessage: (message: SseMessage) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.ok) {
    throw new Error(`Stream request failed with status ${response.status}`);
  }
  if (!response.body) throw new Error("The response does not contain a stream.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  const parser = new SseParser();
  try {
    while (true) {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      const { value, done } = await reader.read();
      if (done) break;
      for (const message of parser.push(decoder.decode(value, { stream: true }))) {
        onMessage(message);
      }
    }
    for (const message of parser.push(decoder.decode())) onMessage(message);
    for (const message of parser.finish()) onMessage(message);
  } finally {
    reader.releaseLock();
  }
}
