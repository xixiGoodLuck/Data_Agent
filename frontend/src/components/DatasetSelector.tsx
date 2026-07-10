import { Database } from "lucide-react";

import type { DatasetSummary } from "../types";

export function DatasetSelector({
  datasets,
  value,
  onChange,
  disabled,
}: {
  datasets: DatasetSummary[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="label mb-2 flex items-center gap-2">
        <Database size={14} /> Dataset
      </span>
      <select
        className="field"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        {datasets.map((dataset) => (
          <option key={dataset.id} value={dataset.id}>
            {dataset.name} · {dataset.row_count.toLocaleString()} rows
          </option>
        ))}
      </select>
    </label>
  );
}
