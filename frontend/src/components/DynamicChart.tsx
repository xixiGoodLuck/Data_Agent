import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartConfig } from "../types";
import { DataTable } from "./DataTable";

const colors = ["#0d7968", "#3b82f6", "#d97706", "#dc2626", "#7c3aed", "#0891b2"];

export function isValidChartConfig(config: ChartConfig | null, columns: string[]): boolean {
  if (!config) return false;
  if (config.type === "table") return true;
  if (config.type === "number") return Boolean(config.y_columns[0] && columns.includes(config.y_columns[0]));
  if (!config.x_column || !columns.includes(config.x_column)) return false;
  return config.y_columns.length > 0 && config.y_columns.every((column) => columns.includes(column));
}

function formatValue(value: unknown, format: ChartConfig["value_format"]): string {
  if (typeof value !== "number") return String(value ?? "");
  if (format === "currency") return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
  if (format === "percent") return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function DynamicChart({
  config,
  columns,
  rows,
}: {
  config: ChartConfig | null;
  columns: string[];
  rows: Record<string, unknown>[];
}) {
  if (!rows.length || !isValidChartConfig(config, columns) || config?.type === "table") {
    return <DataTable columns={columns} rows={rows} />;
  }
  if (!config) return <DataTable columns={columns} rows={rows} />;
  if (config.type === "number") {
    const key = config.y_columns[0];
    return (
      <div className="flex min-h-56 flex-col items-center justify-center border border-zinc-200 bg-zinc-50" style={{ borderRadius: 6 }}>
        <span className="text-sm font-medium text-zinc-500">{config.series_name ?? config.title}</span>
        <strong className="mt-3 text-4xl font-bold text-ink">{formatValue(rows[0]?.[key], config.value_format)}</strong>
      </div>
    );
  }
  const common = (
    <>
      <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" vertical={false} />
      <XAxis dataKey={config.x_column ?? undefined} tick={{ fontSize: 11, fill: "#71717a" }} tickLine={false} axisLine={{ stroke: "#d4d4d8" }} minTickGap={20} />
      <YAxis tick={{ fontSize: 11, fill: "#71717a" }} tickLine={false} axisLine={false} width={64} />
      <Tooltip formatter={(value) => formatValue(value, config.value_format)} contentStyle={{ borderRadius: 6, borderColor: "#d4d4d8", fontSize: 12 }} />
      {config.y_columns.length > 1 ? <Legend /> : null}
    </>
  );
  return (
    <div className="h-[340px] w-full" role="img" aria-label={config.title}>
      <ResponsiveContainer width="100%" height="100%">
        {config.type === "bar" ? (
          <BarChart data={rows} margin={{ top: 12, right: 16, bottom: 24, left: 0 }}>
            {common}
            {config.y_columns.map((column, index) => <Bar key={column} dataKey={column} fill={colors[index % colors.length]} radius={[3, 3, 0, 0]} maxBarSize={54} />)}
          </BarChart>
        ) : config.type === "line" ? (
          <LineChart data={rows} margin={{ top: 12, right: 16, bottom: 24, left: 0 }}>
            {common}
            {config.y_columns.map((column, index) => <Line key={column} type="monotone" dataKey={column} stroke={colors[index % colors.length]} strokeWidth={2} dot={false} />)}
          </LineChart>
        ) : config.type === "area" ? (
          <AreaChart data={rows} margin={{ top: 12, right: 16, bottom: 24, left: 0 }}>
            {common}
            {config.y_columns.map((column, index) => <Area key={column} type="monotone" dataKey={column} stroke={colors[index % colors.length]} fill={colors[index % colors.length]} fillOpacity={0.18} strokeWidth={2} />)}
          </AreaChart>
        ) : config.type === "pie" ? (
          <PieChart>
            <Tooltip formatter={(value) => formatValue(value, config.value_format)} />
            <Legend />
            <Pie data={rows} dataKey={config.y_columns[0]} nameKey={config.x_column ?? undefined} innerRadius="42%" outerRadius="72%" paddingAngle={2}>
              {rows.map((_, index) => <Cell key={index} fill={colors[index % colors.length]} />)}
            </Pie>
          </PieChart>
        ) : (
          <ScatterChart margin={{ top: 12, right: 16, bottom: 24, left: 0 }}>
            {common}
            <Scatter data={rows} fill={colors[0]} />
          </ScatterChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
