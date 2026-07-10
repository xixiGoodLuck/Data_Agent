import { AlertTriangle, RotateCcw } from "lucide-react";

import { useI18n } from "../i18n";

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return <div className="flex min-h-48 flex-col items-center justify-center text-center"><AlertTriangle size={28} className="text-red-600" /><p className="mt-3 max-w-lg text-sm text-zinc-700">{message}</p>{onRetry ? <button className="secondary-button mt-4" onClick={onRetry}><RotateCcw size={16} /> {t("common.retry")}</button> : null}</div>;
}
