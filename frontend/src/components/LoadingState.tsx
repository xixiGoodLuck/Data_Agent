import { LoaderCircle } from "lucide-react";

import { useI18n } from "../i18n";

export function LoadingState({ label }: { label?: string }) {
  const { t } = useI18n();
  return <div className="flex min-h-48 items-center justify-center gap-3 text-sm text-zinc-500"><LoaderCircle size={20} className="animate-spin text-teal-600" /> {label ?? t("common.loading")}</div>;
}
