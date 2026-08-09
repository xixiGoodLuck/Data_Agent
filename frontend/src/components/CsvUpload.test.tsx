import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { I18nProvider } from "../i18n";
import { CsvUpload } from "./CsvUpload";

describe("CsvUpload tabular formats", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("accepts CSV and standard XLSX files", () => {
    localStorage.setItem("insightops-language", "en");
    const { container } = render(
      <I18nProvider>
        <CsvUpload onUploaded={() => undefined} />
      </I18nProvider>,
    );

    expect(container.querySelector('input[type="file"]')).toHaveAttribute("accept", ".csv,.xlsx");
    expect(screen.getByText("Drop CSV or Excel (.xlsx) or choose file")).toBeInTheDocument();
  });
});
