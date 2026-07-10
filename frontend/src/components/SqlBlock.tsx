import { Check, Copy } from "lucide-react";
import { useState } from "react";

export function SqlBlock({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }
  return (
    <div className="overflow-hidden border border-zinc-800 bg-zinc-950 text-zinc-100" style={{ borderRadius: 6 }}>
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2 text-xs text-zinc-400">
        <span>SQLite</span>
        <button className="flex h-7 w-7 items-center justify-center rounded text-zinc-400 hover:bg-white/10 hover:text-white" title="Copy SQL" aria-label="Copy SQL" onClick={() => void copy()}>
          {copied ? <Check size={15} /> : <Copy size={15} />}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-xs leading-6"><code>{sql}</code></pre>
    </div>
  );
}
