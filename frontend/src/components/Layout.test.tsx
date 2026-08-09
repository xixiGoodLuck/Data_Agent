import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { I18nProvider } from "../i18n";
import { TemporaryCredentialsProvider } from "../temporaryCredentials";
import { Layout } from "./Layout";

describe("Layout model status", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("shows the enabled local model instead of mock readiness", () => {
    localStorage.setItem("insightops-language", "en");
    localStorage.setItem(
      "data-agent-local-model",
      JSON.stringify({
        enabled: true,
        base_url: "http://127.0.0.1:1234",
        model: "qwen3.5-0.8b",
      }),
    );

    render(
      <I18nProvider>
        <TemporaryCredentialsProvider>
          <MemoryRouter>
            <Layout />
          </MemoryRouter>
        </TemporaryCredentialsProvider>
      </I18nProvider>,
    );

    expect(screen.getByText("Local model ready: qwen3.5-0.8b")).toBeInTheDocument();
    expect(screen.queryByText("Mock provider ready")).not.toBeInTheDocument();
  });
});
