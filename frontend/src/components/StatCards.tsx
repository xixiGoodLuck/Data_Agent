import { Ban, CheckCircle2, Clock3, Gauge, ShieldAlert, TriangleAlert } from "lucide-react";

import { useI18n } from "../i18n";
import type { StatsOverview } from "../types";

export function StatCards({ stats }: { stats: StatsOverview }) {
  const { formatNumber, t } = useI18n();
  const items = [
    { label: t("stats.totalQueries"), value: formatNumber(stats.total_queries), icon: Gauge, color: "text-blue-600 bg-blue-50" },
    { label: t("stats.successRate"), value: `${stats.success_rate.toFixed(1)}%`, icon: CheckCircle2, color: "text-emerald-600 bg-emerald-50" },
    { label: t("stats.blocked"), value: formatNumber(stats.blocked_count), icon: Ban, color: "text-red-600 bg-red-50" },
    { label: t("stats.pendingApproval"), value: formatNumber(stats.pending_approval_count), icon: ShieldAlert, color: "text-amber-600 bg-amber-50" },
    { label: t("stats.failed"), value: formatNumber(stats.failed_count), icon: TriangleAlert, color: "text-rose-600 bg-rose-50" },
    { label: t("stats.averageLatency"), value: `${stats.average_latency_ms.toFixed(0)} ms`, icon: Clock3, color: "text-violet-600 bg-violet-50" },
  ];
  return <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">{items.map(({ label, value, icon: Icon, color }) => <div key={label} className="panel flex min-h-28 items-start justify-between p-4"><div><div className="text-xs font-medium text-zinc-500">{label}</div><div className="mt-3 text-2xl font-bold text-ink">{value}</div></div><span className={`flex h-9 w-9 items-center justify-center rounded-md ${color}`}><Icon size={18} /></span></div>)}</div>;
}
