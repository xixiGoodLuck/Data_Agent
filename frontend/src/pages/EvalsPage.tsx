import { FlaskConical, Play, Square } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import { consumeSseResponse } from "../api/sse";
import { ErrorState } from "../components/ErrorState";
import { EvalResults } from "../components/EvalResults";
import { useI18n } from "../i18n";
import { useTemporaryCredentials } from "../temporaryCredentials";
import type { EvalRun } from "../types";

interface EvalProgress {
  current: number;
  completed: number;
  total: number;
  case_id: string;
  phase: string;
  node_name?: string | null;
}

function isEvalRun(value: unknown): value is EvalRun {
  if (typeof value !== "object" || value === null) return false;
  const run = value as Partial<EvalRun>;
  return typeof run.id === "string" && typeof run.total_cases === "number";
}

function isProgress(value: unknown): value is EvalProgress {
  if (typeof value !== "object" || value === null) return false;
  const progress = value as Partial<EvalProgress>;
  return (
    typeof progress.current === "number" &&
    typeof progress.completed === "number" &&
    typeof progress.total === "number" &&
    typeof progress.case_id === "string" &&
    typeof progress.phase === "string"
  );
}

export function EvalsPage() {
  const { formatDate, t } = useI18n();
  const { deepseekApiKey } = useTemporaryCredentials();
  const controller = useRef<AbortController | null>(null);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<EvalProgress | null>(null);
  const [category, setCategory] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.latestEval().then(setRun).catch((caught: unknown) => {
      if (!(caught instanceof ApiError && caught.status === 404)) {
        setError(caught instanceof Error ? caught.message : t("evals.loadError"));
      }
    });
    return () => controller.current?.abort();
  }, []);

  const categories = useMemo(
    () => [...new Set(run?.cases.map((item) => item.category) ?? [])].sort(),
    [run],
  );
  const percent = progress?.total
    ? Math.min(100, Math.round((progress.completed / progress.total) * 100))
    : 0;

  function cancel() {
    controller.current?.abort();
    controller.current = null;
    setRunning(false);
    setProgress(null);
  }

  async function execute() {
    controller.current?.abort();
    const abortController = new AbortController();
    controller.current = abortController;
    setRunning(true);
    setProgress(null);
    setError(null);
    let streamError: string | null = null;
    try {
      const response = await api.evalStream(deepseekApiKey, abortController.signal);
      await consumeSseResponse(
        response,
        (message) => {
          if (message.event === "progress" && isProgress(message.data)) {
            setProgress(message.data);
          } else if (message.event === "case_result" && isProgress(message.data)) {
            setProgress(message.data);
          } else if (message.event === "result" && isEvalRun(message.data)) {
            setRun(message.data);
          } else if (
            message.event === "error" &&
            typeof message.data === "object" &&
            message.data !== null
          ) {
            const payload = message.data as { message?: string };
            streamError = payload.message ?? t("evals.runError");
          }
        },
        abortController.signal,
      );
      if (streamError) throw new Error(streamError);
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setError(caught instanceof Error ? caught.message : t("evals.runError"));
      }
    } finally {
      if (controller.current === abortController) controller.current = null;
      setRunning(false);
      setProgress(null);
    }
  }

  if (error && !run) return <ErrorState message={error} onRetry={() => void execute()} />;

  return (
    <div className="space-y-6">
      <section className="panel flex flex-wrap items-center gap-4 p-5">
        <span className="flex h-10 w-10 items-center justify-center rounded-md bg-violet-50 text-violet-700">
          <FlaskConical size={20} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-bold text-ink">{t("evals.title")}</h2>
          <p className="mt-1 text-xs text-zinc-500">{t("evals.subtitle")}</p>
        </div>
        {running ? (
          <button className="secondary-button" onClick={cancel}>
            <Square size={15} fill="currentColor" /> {t("evals.cancel")}
          </button>
        ) : (
          <button className="command-button" onClick={() => void execute()}>
            <Play size={16} fill="currentColor" /> {t("evals.run")}
          </button>
        )}
      </section>

      {running ? (
        <section className="panel p-5" aria-live="polite">
          <div className="flex items-center justify-between gap-4 text-xs">
            <span className="min-w-0 truncate font-semibold text-ink">
              {progress
                ? t("evals.progress", {
                    current: progress.current,
                    total: progress.total,
                    case: progress.case_id,
                  })
                : t("evals.preparing")}
            </span>
            <span className="shrink-0 tabular-nums text-zinc-500">{percent}%</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded bg-zinc-100">
            <div
              className="h-full bg-violet-600 transition-[width] duration-300"
              style={{ width: `${percent}%` }}
            />
          </div>
          {progress?.node_name ? (
            <p className="mt-2 truncate font-mono text-xs text-zinc-500">
              {progress.node_name}
            </p>
          ) : null}
        </section>
      ) : null}

      {error && run ? (
        <div className="border-l-2 border-red-500 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {run ? (
        <section className="panel p-5 lg:p-6">
          <div className="mb-6 flex flex-wrap items-end gap-4 border-b border-zinc-200 pb-5">
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-bold text-ink">
                {t("evals.passed", { passed: run.passed_cases, total: run.total_cases })}
              </h2>
              <p className="mt-1 text-xs text-zinc-500">
                {t("evals.summary", {
                  date: formatDate(run.created_at),
                  average: run.average_latency_ms.toFixed(1),
                  p95: run.p95_latency_ms.toFixed(1),
                })}
              </p>
            </div>
            <label>
              <span className="label mb-2 block">{t("common.category")}</span>
              <select
                className="field min-w-56"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
              >
                <option value="">{t("common.allCategories")}</option>
                {categories.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
          </div>
          <EvalResults run={run} category={category || undefined} />
        </section>
      ) : !running ? (
        <section className="panel py-20 text-center text-sm text-zinc-500">
          {t("evals.none")}
        </section>
      ) : null}
    </div>
  );
}
