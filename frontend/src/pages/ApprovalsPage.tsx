import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { ApprovalCard } from "../components/ApprovalCard";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useI18n } from "../i18n";
import type { ApprovalRequest } from "../types";

export function ApprovalsPage() {
  const { formatDate, label, t } = useI18n();
  const [items, setItems] = useState<ApprovalRequest[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  async function load() { setItems(await api.approvals()); setLoading(false); }
  useEffect(() => { void load().catch((caught: unknown) => { setError(caught instanceof Error ? caught.message : t("approvals.loadError")); setLoading(false); }); }, []);
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  async function decide(id: string, approved: boolean, note: string) { setBusy(id); try { await api.decideApproval(id, approved, note); await load(); } catch (caught) { setError(caught instanceof Error ? caught.message : t("approvals.decisionError")); } finally { setBusy(null); } }
  const pending = items.filter((item) => item.status === "pending");
  const history = items.filter((item) => item.status !== "pending");
  return <div className="space-y-6"><section><div className="mb-4 flex items-center gap-2"><ShieldCheck size={19} className="text-amber-700" /><h2 className="text-sm font-bold text-ink">{t("approvals.pending")}</h2><span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">{pending.length}</span></div><div className="grid gap-4 xl:grid-cols-2">{pending.map((approval) => <ApprovalCard key={approval.id} approval={approval} busy={busy === approval.id} onDecision={(approved, note) => void decide(approval.id, approved, note)} />)}{!pending.length ? <div className="panel col-span-full py-16 text-center text-sm text-zinc-500">{t("approvals.none")}</div> : null}</div></section>{history.length ? <section className="panel overflow-hidden"><div className="border-b border-zinc-200 px-5 py-4"><h2 className="text-sm font-bold text-ink">{t("approvals.history")}</h2></div><div className="divide-y divide-zinc-100">{history.map((approval) => <div key={approval.id} className="grid gap-2 px-5 py-4 md:grid-cols-[100px_minmax(0,1fr)_180px]"><span className={`w-fit rounded px-2 py-1 text-xs font-semibold ${approval.status === "approved" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>{label("status", approval.status)}</span><div><div className="text-sm font-medium text-ink">{approval.question}</div><div className="mt-1 truncate text-xs text-zinc-500">{approval.reasons.join(" · ")}</div></div><div className="text-xs text-zinc-500">{approval.decided_at ? formatDate(approval.decided_at) : "—"}</div></div>)}</div></section> : null}</div>;
}
