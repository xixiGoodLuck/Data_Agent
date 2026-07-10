import { ShieldAlert, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

export interface ApprovalCardData {
  id: string;
  question?: string | null;
  risk_level: string;
  reasons: string[];
  sql_preview: string;
  selected_columns?: string[];
  status?: string;
}

export function ApprovalCard({
  approval,
  onDecision,
  busy = false,
}: {
  approval: ApprovalCardData;
  onDecision?: (approved: boolean, note: string) => void;
  busy?: boolean;
}) {
  const [note, setNote] = useState("");
  return (
    <section className="border border-amber-300 bg-amber-50 p-4" style={{ borderRadius: 8 }}>
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 shrink-0 text-amber-700" size={21} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-bold text-amber-950">Sensitive query approval</h3>
            <span className="rounded bg-amber-200 px-2 py-0.5 text-xs font-bold uppercase text-amber-900">{approval.risk_level}</span>
          </div>
          {approval.question ? <p className="mt-2 text-sm text-amber-950">{approval.question}</p> : null}
          <ul className="mt-3 space-y-1 text-sm text-amber-900">{approval.reasons.map((reason) => <li key={reason}>• {reason}</li>)}</ul>
          {approval.selected_columns?.length ? <p className="mt-3 text-xs text-amber-800">Columns: {approval.selected_columns.join(", ")}</p> : null}
          <pre className="mt-3 max-h-40 overflow-auto rounded bg-zinc-950 p-3 text-xs leading-5 text-zinc-100"><code>{approval.sql_preview}</code></pre>
          {onDecision ? (
            <div className="mt-3 space-y-3">
              <input className="field border-amber-300" value={note} maxLength={500} placeholder="Decision note (optional)" onChange={(event) => setNote(event.target.value)} />
              <div className="flex flex-wrap gap-2">
                <button className="command-button" disabled={busy} onClick={() => onDecision(true, note)}><ThumbsUp size={16} /> Approve</button>
                <button className="secondary-button border-red-200 text-red-700 hover:bg-red-50" disabled={busy} onClick={() => onDecision(false, note)}><ThumbsDown size={16} /> Reject</button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
