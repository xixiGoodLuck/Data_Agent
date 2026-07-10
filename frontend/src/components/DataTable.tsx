import type { ReactNode } from "react";

function display(value: unknown): ReactNode {
  if (value === null || value === undefined) return <span className="text-zinc-400">null</span>;
  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function DataTable({
  columns,
  rows,
  emptyMessage = "No rows returned.",
}: {
  columns: string[];
  rows: Record<string, unknown>[];
  emptyMessage?: string;
}) {
  if (!rows.length || !columns.length) {
    return <div className="py-12 text-center text-sm text-zinc-500">{emptyMessage}</div>;
  }
  return (
    <div className="max-h-[440px] overflow-auto border border-zinc-200" style={{ borderRadius: 6 }}>
      <table className="min-w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-zinc-100">
          <tr>
            {columns.map((column) => (
              <th key={column} className="whitespace-nowrap border-b border-zinc-200 px-3 py-2 text-left text-xs font-semibold text-zinc-600">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white">
          {rows.map((row, index) => (
            <tr key={index} className="hover:bg-zinc-50">
              {columns.map((column) => (
                <td key={column} className="max-w-[320px] truncate whitespace-nowrap px-3 py-2 text-zinc-700" title={String(row[column] ?? "null")}>
                  {display(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
