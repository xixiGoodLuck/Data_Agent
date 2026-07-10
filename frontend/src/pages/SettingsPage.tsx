import { Cpu, KeyRound, Server, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useI18n } from "../i18n";
import type { PublicSettings } from "../types";

export function SettingsPage() {
  const { formatNumber, t } = useI18n();
  const [settings, setSettings] = useState<PublicSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void api.settings().then(setSettings).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : t("settings.loadError"))); }, []);
  if (error) return <ErrorState message={error} />;
  if (!settings) return <LoadingState />;
  const details = [{ label: t("settings.provider"), value: settings.provider, icon: Cpu }, { label: t("settings.model"), value: settings.model, icon: Server }, { label: t("settings.resultLimit"), value: `${formatNumber(settings.max_result_rows)} ${t("common.rows")}`, icon: ShieldCheck }, { label: t("settings.queryTimeout"), value: `${settings.query_timeout_seconds}s`, icon: KeyRound }];
  return <div className="space-y-6"><section className="panel p-5 lg:p-6"><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{details.map(({ label, value, icon: Icon }) => <div key={label} className="border-l-2 border-teal-500 bg-zinc-50 p-4"><Icon size={17} className="text-zinc-500" /><div className="mt-4 text-xs text-zinc-500">{label}</div><div className="mt-1 break-words text-sm font-bold text-ink">{value}</div></div>)}</div></section><section className="panel p-5 lg:p-6"><h2 className="text-sm font-bold text-ink">{t("settings.providerEnvironment")}</h2><p className="mt-2 text-sm leading-6 text-zinc-600">{t("settings.providerHelp")}</p><pre className="mt-5 overflow-x-auto rounded-md bg-zinc-950 p-4 text-xs leading-6 text-zinc-100"><code>{`LLM_PROVIDER=openai_compatible\nOPENAI_API_KEY=\nOPENAI_BASE_URL=https://api.openai.com/v1\nOPENAI_MODEL=gpt-4.1-mini\nLLM_TIMEOUT_SECONDS=45`}</code></pre></section><section className="panel p-5 lg:p-6"><h2 className="text-sm font-bold text-ink">{t("settings.publicLimits")}</h2><dl className="mt-4 grid gap-4 sm:grid-cols-3"><div><dt className="text-xs text-zinc-500">{t("settings.uploadBytes")}</dt><dd className="mt-1 text-sm font-semibold text-ink">{(settings.upload_limits.max_bytes / 1024 / 1024).toFixed(0)} MB</dd></div><div><dt className="text-xs text-zinc-500">{t("settings.uploadRows")}</dt><dd className="mt-1 text-sm font-semibold text-ink">{formatNumber(settings.upload_limits.max_rows)}</dd></div><div><dt className="text-xs text-zinc-500">{t("settings.uploadColumns")}</dt><dd className="mt-1 text-sm font-semibold text-ink">{settings.upload_limits.max_columns}</dd></div></dl></section></div>;
}
