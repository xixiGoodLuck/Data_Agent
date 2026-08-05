import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, parseApiResponse, parseQueryResponse } from "./client";

describe("API response parsing", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns a valid JSON payload", async () => {
    const response = new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
    await expect(parseApiResponse<{ status: string }>(response)).resolves.toEqual({ status: "ok" });
  });

  it("turns a stable backend error into ApiError", async () => {
    const response = new Response(
      JSON.stringify({ error: { type: "dataset_not_found", message: "Missing" } }),
      { status: 404, headers: { "Content-Type": "application/json" } },
    );
    await expect(parseApiResponse(response)).rejects.toMatchObject({
      type: "dataset_not_found",
      message: "Missing",
      status: 404,
    });
  });

  it("rejects incomplete query responses", () => {
    expect(() => parseQueryResponse({ status: "success" })).toThrow(ApiError);
  });

  it("sends the local model again when resuming an approval", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "success" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const localModel = {
      enabled: true,
      base_url: "http://127.0.0.1:1234",
      model: "qwen3.5-0.8b",
    };

    await api.decideApproval("approval-1", true, "reviewed", "", localModel);

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      note: "reviewed",
      local_model: localModel,
    });
  });
});
