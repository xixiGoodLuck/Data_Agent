import { describe, expect, it } from "vitest";

import type { ChartConfig } from "../types";
import { isValidChartConfig } from "./DynamicChart";

describe("chart fallback validation", () => {
  const config: ChartConfig = {
    type: "bar",
    x_column: "category",
    y_columns: ["revenue"],
    title: "Revenue",
    value_format: "currency",
  };

  it("accepts a config grounded in result columns", () => {
    expect(isValidChartConfig(config, ["category", "revenue"])).toBe(true);
  });

  it("rejects fabricated axis fields", () => {
    expect(isValidChartConfig(config, ["category", "amount"])).toBe(false);
  });

  it("validates scalar cards without an x axis", () => {
    expect(
      isValidChartConfig(
        { ...config, type: "number", x_column: null, y_columns: ["revenue"] },
        ["revenue"],
      ),
    ).toBe(true);
  });
});
