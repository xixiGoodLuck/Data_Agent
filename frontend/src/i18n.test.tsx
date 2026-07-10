import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { I18nProvider, useI18n } from "./i18n";

function Probe() {
  const { datasetText, language, setLanguage, t } = useI18n();
  const dataset = datasetText("commerce", { name: "Fallback", description: "", questions: [] });
  return (
    <div>
      <span>{language}</span>
      <span>{t("nav.dashboard")}</span>
      <span>{dataset.name}</span>
      <button onClick={() => setLanguage("en")}>English</button>
    </div>
  );
}

describe("I18nProvider", () => {
  afterEach(() => window.localStorage.clear());

  it("loads a stored language and persists language changes", () => {
    window.localStorage.setItem("insightops-language", "zh");
    render(<I18nProvider><Probe /></I18nProvider>);

    expect(screen.getByText("仪表盘")).toBeInTheDocument();
    expect(screen.getByText("电商运营")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("zh-CN");

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Commerce Operations")).toBeInTheDocument();
    expect(window.localStorage.getItem("insightops-language")).toBe("en");
    expect(document.documentElement.lang).toBe("en");
  });
});
