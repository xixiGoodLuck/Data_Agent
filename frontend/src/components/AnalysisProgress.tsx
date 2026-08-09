import { CheckCircle2, CircleDot, GitBranch, LoaderCircle } from "lucide-react";

import { useI18n } from "../i18n";
import type { TraceEvent } from "../types";

export function eventPayload(event: TraceEvent): Record<string, unknown> {
  if (!event.output_summary) return {};
  try {
    const parsed = JSON.parse(event.output_summary) as unknown;
    return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

export function AnalysisProgress({ events, live = false }: { events: TraceEvent[]; live?: boolean }) {
  const { t } = useI18n();
  const businessEvents = events.filter((event) => [
    "analysis_step_started",
    "evidence_created",
    "analysis_decision",
    "final_synthesis_started",
    "final_synthesis_completed",
  ].includes(event.event_type));
  if (!businessEvents.length) return null;
  return (
    <section aria-label={t("analysis.progress")} className="space-y-3">
      <div className="flex items-center gap-2">
        <h3 className="label">{t("analysis.progress")}</h3>
        {live ? <LoaderCircle aria-label={t("analysis.live")} className="animate-spin text-teal-600" size={15} /> : null}
      </div>
      <ol className="space-y-2">
        {businessEvents.map((event) => {
          const payload = eventPayload(event);
          const text = event.event_type === "analysis_step_started"
            ? String(payload.question ?? t("analysis.stepStarted"))
            : event.event_type === "evidence_created"
              ? String(payload.result_summary ?? t("analysis.evidenceCreated"))
              : event.event_type === "analysis_decision"
                ? String(payload.reason ?? t("analysis.decision"))
                : event.event_type === "final_synthesis_started"
                  ? t("analysis.synthesizing")
                  : t("analysis.synthesisComplete");
          const Icon = event.event_type === "analysis_decision" ? GitBranch : event.event_type === "evidence_created" ? CheckCircle2 : CircleDot;
          return <li key={event.id ?? `${event.step_index}-${event.event_type}`} className="flex gap-2 text-sm leading-5 text-zinc-700"><Icon className="mt-0.5 shrink-0 text-teal-700" size={15} /><span>{text}</span></li>;
        })}
      </ol>
    </section>
  );
}
