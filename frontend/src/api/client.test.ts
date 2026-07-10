import { describe, expect, it } from "vitest";

import { ApiError, parseApiResponse, parseQueryResponse } from "./client";

describe("API response parsing", () => {
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
});
