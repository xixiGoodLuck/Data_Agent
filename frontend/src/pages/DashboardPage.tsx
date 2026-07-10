import { Activity, BarChart3, Clock3 } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { DynamicChart } from "../components/DynamicChart";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { QueryLogTable } from "../components/QueryLogTable";
import { StatCards } from "../components/StatCards";
import type { ChartConfig, StatsOverview } from "../types";

export function DashboardPage() {
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      setStats(await api.stats());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Dashboard failed to load.");
    }
  }

  useEffect(() => void load(), []);
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!stats) return <LoadingState label="Loading operations metrics" />;

  const chartRows = stats.chart_breakdown.map((item) => ({ chart_type: item.type, count: item.count }));
  const chartConfig: ChartConfig = {
    type: "bar",
    x_column: "chart_type",
    y_columns: ["count"],
    title: "Chart distribution",
    value_format: "number",
  };

  return (
    <div className="space-y-6">
      <StatCards stats={stats} />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.7fr)]">
        <section className="panel p-5">
          <div className="mb-5 flex items-center justify-between">
            <div><h2 className="text-sm font-bold text-ink">Visualization mix</h2><p className="mt-1 text-xs text-zinc-500">Interactive query results by chart plan</p></div>
            <BarChart3 size={19} className="text-zinc-400" />
          </div>
          {chartRows.length ? <DynamicChart config={chartConfig} columns={["chart_type", "count"]} rows={chartRows} /> : <div className="flex h-[340px] items-center justify-center text-sm text-zinc-500">No chart activity yet.</div>}
        </section>
        <section className="panel p-5">
          <div className="mb-5 flex items-center justify-between"><div><h2 className="text-sm font-bold text-ink">Runtime</h2><p className="mt-1 text-xs text-zinc-500">Latency and fallback health</p></div><Activity size={19} className="text-zinc-400" /></div>
          <div className="space-y-5">
            <div className="border-b border-zinc-100 pb-4"><div className="flex items-center gap-2 text-xs text-zinc-500"><Clock3 size={14} /> p95 latency</div><div className="mt-2 text-3xl font-bold text-ink">{stats.p95_latency_ms.toFixed(0)} <span className="text-sm font-medium text-zinc-400">ms</span></div></div>
            <div><div className="text-xs text-zinc-500">Fallback rate</div><div className="mt-2 text-3xl font-bold text-ink">{stats.fallback_rate.toFixed(1)}%</div></div>
            <div><div className="mb-2 text-xs font-medium text-zinc-500">Top datasets</div><div className="space-y-3">{stats.top_datasets.map((dataset) => <div key={dataset.dataset_id} className="flex items-center gap-3"><span className="min-w-0 flex-1 truncate text-sm text-zinc-700">{dataset.name ?? dataset.dataset_id}</span><span className="text-sm font-semibold tabular-nums text-ink">{dataset.count}</span></div>)}{!stats.top_datasets.length ? <p className="text-sm text-zinc-500">No query activity yet.</p> : null}</div></div>
          </div>
        </section>
      </div>
      <section className="panel overflow-hidden">
        <div className="border-b border-zinc-200 px-5 py-4"><h2 className="text-sm font-bold text-ink">Recent queries</h2></div>
        <QueryLogTable logs={stats.recent_queries} />
      </section>
      {stats.recent_failures.length ? <section className="panel overflow-hidden"><div className="border-b border-zinc-200 px-5 py-4"><h2 className="text-sm font-bold text-ink">Recent blocked and failed</h2></div><QueryLogTable logs={stats.recent_failures} /></section> : null}
    </div>
  );
}
