import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { I18nProvider } from "../i18n";
import type { DatasetDetail } from "../types";
import { DatasetsPage } from "./DatasetsPage";

const builtinDataset: DatasetDetail = {
  id: "sales",
  name: "Sales",
  description: "Built-in sales",
  source_type: "sample",
  source_filename: null,
  sheet_name: null,
  tables: ["sales"],
  table_count: 1,
  column_count: 1,
  row_count: 1,
  is_builtin: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  suggested_questions: [],
  schema: { sales: { columns: [{ name: "value", type: "INTEGER", nullable: false, primary_key: false }], foreign_keys: [], sample_rows: [] } },
  column_mapping: [],
  preview: [{ value: 1 }],
};

const uploadedDataset: DatasetDetail = {
  ...builtinDataset,
  id: "upload-1",
  name: "test.xlsx",
  description: "Uploaded Excel",
  source_type: "excel_upload",
  source_filename: "test.xlsx",
  sheet_name: "Sheet1",
  tables: ["data"],
  is_builtin: false,
  schema: { data: builtinDataset.schema.sales },
};

describe("DatasetsPage removal", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("shows separate actions and requires confirmation before deleting an upload", async () => {
    localStorage.setItem("insightops-language", "en");
    vi.spyOn(api, "datasets")
      .mockResolvedValueOnce([builtinDataset, uploadedDataset])
      .mockResolvedValueOnce([builtinDataset]);
    vi.spyOn(api, "dataset").mockResolvedValue(builtinDataset);
    const deleteDataset = vi.spyOn(api, "deleteDataset").mockResolvedValue({ status: "deleted" });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<I18nProvider><DatasetsPage /></I18nProvider>);

    expect(await screen.findByRole("button", { name: "Remove built-in dataset: Sales Performance" })).toBeInTheDocument();
    const deleteUpload = screen.getByRole("button", { name: "Permanently delete uploaded dataset: test.xlsx" });
    fireEvent.click(deleteUpload);
    expect(deleteDataset).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.click(deleteUpload);

    await waitFor(() => expect(deleteDataset).toHaveBeenCalledWith("upload-1"));
    expect(screen.queryByRole("button", { name: "Permanently delete uploaded dataset: test.xlsx" })).not.toBeInTheDocument();
  });

  it("removes a builtin and restores builtin examples without affecting uploads", async () => {
    localStorage.setItem("insightops-language", "en");
    vi.spyOn(api, "datasets")
      .mockResolvedValueOnce([builtinDataset, uploadedDataset])
      .mockResolvedValueOnce([uploadedDataset])
      .mockResolvedValueOnce([builtinDataset, uploadedDataset]);
    vi.spyOn(api, "dataset").mockImplementation(async (id) => id === "sales" ? builtinDataset : uploadedDataset);
    vi.spyOn(api, "deleteDataset").mockResolvedValue({ status: "disabled" });
    const restore = vi.spyOn(api, "restoreBuiltinDatasets").mockResolvedValue({ status: "restored", dataset_ids: ["sales"] });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<I18nProvider><DatasetsPage /></I18nProvider>);

    fireEvent.click(await screen.findByRole("button", { name: "Remove built-in dataset: Sales Performance" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Remove built-in dataset: Sales Performance" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Permanently delete uploaded dataset: test.xlsx" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Restore built-in examples" }));

    await waitFor(() => expect(restore).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: "Remove built-in dataset: Sales Performance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Permanently delete uploaded dataset: test.xlsx" })).toBeInTheDocument();
  });
});
