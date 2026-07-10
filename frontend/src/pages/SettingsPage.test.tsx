import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { TemporaryCredentialsProvider } from "../temporaryCredentials";
import { SettingsPage } from "./SettingsPage";

describe("SettingsPage temporary DeepSeek key", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the key in memory and supports show and clear controls", async () => {
    vi.spyOn(api, "settings").mockResolvedValue({
      provider: "mock",
      mode: "mock",
      model: "deterministic-mock",
      upload_limits: { max_bytes: 10_485_760, max_rows: 100_000, max_columns: 100 },
      max_result_rows: 100,
      query_timeout_seconds: 2,
    });
    render(
      <TemporaryCredentialsProvider>
        <SettingsPage />
      </TemporaryCredentialsProvider>,
    );

    const input = await screen.findByLabelText("DeepSeek API key");
    expect(input).toHaveAttribute("type", "password");
    fireEvent.change(input, { target: { value: "sk-page-only" } });
    expect(input).toHaveValue("sk-page-only");
    expect(screen.getByText("Active for this page")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show API key" }));
    expect(input).toHaveAttribute("type", "text");

    fireEvent.click(screen.getByRole("button", { name: "Clear API key" }));
    expect(input).toHaveValue("");
    expect(screen.getByText("Not set")).toBeInTheDocument();
  });
});
