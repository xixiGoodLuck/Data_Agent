import { AlertTriangle, RotateCcw } from "lucide-react";

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="flex min-h-48 flex-col items-center justify-center text-center"><AlertTriangle size={28} className="text-red-600" /><p className="mt-3 max-w-lg text-sm text-zinc-700">{message}</p>{onRetry ? <button className="secondary-button mt-4" onClick={onRetry}><RotateCcw size={16} /> Retry</button> : null}</div>;
}
