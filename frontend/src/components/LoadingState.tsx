import { LoaderCircle } from "lucide-react";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return <div className="flex min-h-48 items-center justify-center gap-3 text-sm text-zinc-500"><LoaderCircle size={20} className="animate-spin text-teal-600" /> {label}</div>;
}
