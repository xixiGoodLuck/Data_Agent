import { FileUp, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";

import { uploadDataset } from "../api/client";
import type { DatasetDetail } from "../types";

export function CsvUpload({ onUploaded }: { onUploaded: (dataset: DatasetDetail) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File) {
    setError(null);
    setProgress(0);
    try {
      const dataset = await uploadDataset(file, setProgress);
      setProgress(100);
      onUploaded(dataset);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed.");
    } finally {
      window.setTimeout(() => setProgress(null), 600);
    }
  }

  return (
    <div>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void upload(file);
          event.currentTarget.value = "";
        }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file) void upload(file);
        }}
        className={`flex min-h-40 w-full flex-col items-center justify-center border border-dashed p-6 text-center transition ${
          dragging ? "border-teal-500 bg-teal-50" : "border-zinc-300 bg-zinc-50 hover:bg-white"
        }`}
        style={{ borderRadius: 8 }}
      >
        <UploadCloud className="mb-3 text-teal-600" size={28} />
        <span className="text-sm font-semibold text-ink">Drop CSV or choose file</span>
        <span className="mt-1 text-xs text-zinc-500">UTF-8 · 10 MB · 100,000 rows</span>
      </button>
      {progress !== null ? (
        <div className="mt-3 flex items-center gap-3 text-sm text-zinc-600">
          <FileUp size={16} />
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-200">
            <div className="h-full bg-teal-600 transition-all" style={{ width: `${progress}%` }} />
          </div>
          <span className="w-10 text-right tabular-nums">{progress}%</span>
        </div>
      ) : null}
      {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
    </div>
  );
}
