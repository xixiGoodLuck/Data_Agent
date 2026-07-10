import { Database } from "lucide-react";

import { useI18n } from "../i18n";
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
  const { datasetText, formatNumber, t } = useI18n();
  return (
    <label className="block">
      <span className="label mb-2 flex items-center gap-2">
        <Database size={14} /> {t("common.dataset")}
      </span>
      <select
        className="field"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        {datasets.map((dataset) => (
          <option key={dataset.id} value={dataset.id}>
            {datasetText(dataset.id, { name: dataset.name, description: "", questions: [] }).name} · {formatNumber(dataset.row_count)} {t("common.rows")}
          </option>
        ))}
      </select>
    </label>
  );
}
