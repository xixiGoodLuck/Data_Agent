import { CheckCircle2, Circle, LoaderCircle, ShieldAlert, XCircle } from "lucide-react";

import { useI18n } from "../i18n";
import type { TraceEvent } from "../types";

function EventIcon({ event }: { event: TraceEvent }) {
  if (event.status === "running") return <LoaderCircle className="animate-spin text-blue-600" size={16} />;
  if (["failed", "blocked", "rejected"].includes(event.status)) return <XCircle className="text-red-600" size={16} />;
  if (event.event_type === "approval_required") return <ShieldAlert className="text-amber-600" size={16} />;
  if (["completed", "success", "approved"].includes(event.status)) return <CheckCircle2 className="text-teal-600" size={16} />;
  return <Circle className="text-zinc-400" size={16} />;
}

export function AgentTrace({ events, live = false }: { events: TraceEvent[]; live?: boolean }) {
  const { label, t } = useI18n();
  if (!events.length) return <div className="py-8 text-center text-sm text-zinc-500">{t("trace.empty")}</div>;
  return (
    <ol className="space-y-0">
      {events.map((event, index) => (
        <li key={event.id ?? `${event.step_index}-${index}`} className="relative flex gap-3 pb-4 last:pb-0">
          {index < events.length - 1 ? <span className="absolute left-[7px] top-5 h-[calc(100%-8px)] w-px bg-zinc-200" /> : null}
          <span className="relative z-10 mt-0.5 bg-white"><EventIcon event={event} /></span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2">
              <span className="text-sm font-medium text-ink">{label("node", event.node_name)}</span>
              <span className="text-xs text-zinc-400">{label("event", event.event_type)}</span>
              <span className="ml-auto text-xs tabular-nums text-zinc-400">{event.latency_ms.toFixed(1)} ms</span>
            </div>
            {event.output_summary ? <p className="mt-1 truncate text-xs text-zinc-500" title={event.output_summary}>{event.output_summary}</p> : null}
          </div>
        </li>
      ))}
      {live ? <li className="mt-3 flex items-center gap-2 text-xs font-medium text-blue-700"><LoaderCircle size={14} className="animate-spin" /> {t("trace.running")}</li> : null}
    </ol>
  );
}
