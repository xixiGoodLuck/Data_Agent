import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  DEEPSEEK_API_KEY_HEADER,
  TemporaryCredentialsProvider,
  deepseekRequestHeaders,
  useTemporaryCredentials,
} from "./temporaryCredentials";

function Probe() {
  const { clearDeepseekApiKey, deepseekApiKey, setDeepseekApiKey } =
    useTemporaryCredentials();
  return (
    <div>
      <span data-testid="key">{deepseekApiKey}</span>
      <button onClick={() => setDeepseekApiKey("sk-temporary")}>Set</button>
      <button onClick={clearDeepseekApiKey}>Clear</button>
    </div>
  );
}

describe("temporary DeepSeek credentials", () => {
  afterEach(cleanup);

  it("adds a request header only for a non-empty key", () => {
    expect(deepseekRequestHeaders("  ")).toEqual({});
    expect(deepseekRequestHeaders("  sk-test  ")).toEqual({
      [DEEPSEEK_API_KEY_HEADER]: "sk-test",
    });
  });

  it("clears the in-memory key when the page is hidden", () => {
    render(<TemporaryCredentialsProvider><Probe /></TemporaryCredentialsProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Set" }));
    expect(screen.getByTestId("key")).toHaveTextContent("sk-temporary");

    fireEvent(window, new PageTransitionEvent("pagehide"));

    expect(screen.getByTestId("key")).toBeEmptyDOMElement();
  });

  it("does not retain a key after the provider is remounted", () => {
    const view = render(<TemporaryCredentialsProvider><Probe /></TemporaryCredentialsProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Set" }));
    view.unmount();

    render(<TemporaryCredentialsProvider><Probe /></TemporaryCredentialsProvider>);

    expect(screen.getByTestId("key")).toBeEmptyDOMElement();
  });
});
