import { FlaskConical, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiError, api } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { EvalResults } from "../components/EvalResults";
import { LoadingState } from "../components/LoadingState";
import { useI18n } from "../i18n";
import type { EvalRun } from "../types";

export function EvalsPage() {
  const { formatDate, t } = useI18n();
  const [run, setRun] = useState<EvalRun | null>(null);
  const [running, setRunning] = useState(false);
  const [category, setCategory] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void api.latestEval().then(setRun).catch((caught: unknown) => { if (!(caught instanceof ApiError && caught.status === 404)) setError(caught instanceof Error ? caught.message : t("evals.loadError")); }); }, []);
  const categories = useMemo(() => [...new Set(run?.cases.map((item) => item.category) ?? [])].sort(), [run]);
  async function execute() { setRunning(true); setError(null); try { setRun(await api.runEval()); } catch (caught) { setError(caught instanceof Error ? caught.message : t("evals.runError")); } finally { setRunning(false); } }
  if (error && !run) return <ErrorState message={error} onRetry={() => void execute()} />;
  return <div className="space-y-6"><section className="panel flex flex-wrap items-center gap-4 p-5"><span className="flex h-10 w-10 items-center justify-center rounded-md bg-violet-50 text-violet-700"><FlaskConical size={20} /></span><div className="min-w-0 flex-1"><h2 className="text-sm font-bold text-ink">{t("evals.title")}</h2><p className="mt-1 text-xs text-zinc-500">{t("evals.subtitle")}</p></div><button className="command-button" disabled={running} onClick={() => void execute()}><Play size={16} fill="currentColor" /> {running ? t("evals.running") : t("evals.run")}</button></section>{running ? <section className="panel"><LoadingState label={t("evals.executing")} /></section> : null}{run ? <section className="panel p-5 lg:p-6"><div className="mb-6 flex flex-wrap items-end gap-4 border-b border-zinc-200 pb-5"><div className="min-w-0 flex-1"><h2 className="text-lg font-bold text-ink">{t("evals.passed", { passed: run.passed_cases, total: run.total_cases })}</h2><p className="mt-1 text-xs text-zinc-500">{t("evals.summary", { date: formatDate(run.created_at), average: run.average_latency_ms.toFixed(1), p95: run.p95_latency_ms.toFixed(1) })}</p></div><label><span className="label mb-2 block">{t("common.category")}</span><select className="field min-w-56" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">{t("common.allCategories")}</option>{categories.map((item) => <option key={item}>{item}</option>)}</select></label></div><EvalResults run={run} category={category || undefined} /></section> : !running ? <section className="panel py-20 text-center text-sm text-zinc-500">{t("evals.none")}</section> : null}</div>;
}
