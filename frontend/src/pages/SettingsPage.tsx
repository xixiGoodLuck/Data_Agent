import {
  Cpu,
  Eye,
  EyeOff,
  KeyRound,
  Server,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useI18n } from "../i18n";
import { useTemporaryCredentials } from "../temporaryCredentials";
import type { PublicSettings } from "../types";

export function SettingsPage() {
  const { formatNumber, t } = useI18n();
  const {
    clearDeepseekApiKey,
    deepseekApiKey,
    hasDeepseekApiKey,
    setDeepseekApiKey,
    localModel,
    saveLocalModel,
    restoreDefaultModel,
  } = useTemporaryCredentials();
  const [settings, setSettings] = useState<PublicSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);
  const [localBaseUrl, setLocalBaseUrl] = useState(localModel.base_url);
  const [localModelId, setLocalModelId] = useState(localModel.model);
  const [localModelOpen, setLocalModelOpen] = useState(false);
  const [localModelError, setLocalModelError] = useState<string | null>(null);

  useEffect(() => {
    void api.settings().then(setSettings).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : t("settings.loadError"));
    });
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!settings) return <LoadingState />;

  const effectiveProvider = localModel.enabled
    ? "local"
    : hasDeepseekApiKey
      ? "deepseek"
      : settings.provider;
  const effectiveModel = localModel.enabled
    ? localModel.model
    : hasDeepseekApiKey
      ? "deepseek-v4-flash"
      : settings.model;
  const details = [
    { label: t("settings.provider"), value: effectiveProvider, icon: Cpu },
    { label: t("settings.model"), value: effectiveModel, icon: Server },
    {
      label: t("settings.resultLimit"),
      value: `${formatNumber(settings.max_result_rows)} ${t("common.rows")}`,
      icon: ShieldCheck,
    },
    {
      label: t("settings.queryTimeout"),
      value: `${settings.query_timeout_seconds}s`,
      icon: KeyRound,
    },
  ];

  return (
    <div className="space-y-6">
      <section className="panel p-5 lg:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-bold text-ink">本地模型</h2>
          {localModel.enabled ? <span className="rounded bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">✓ 本地模型：{localModel.model}</span> : null}
          <button type="button" className="secondary-button" onClick={() => setLocalModelOpen((value) => !value)}>本地模型</button>
        </div>
        {localModelOpen ? <div className="mt-4 grid gap-3 border-t border-zinc-100 pt-4">
          <label><span className="label mb-2 block">Base URL</span><input className="field" value={localBaseUrl} onChange={(event) => setLocalBaseUrl(event.target.value)} placeholder="http://127.0.0.1:1234" /></label>
          <label><span className="label mb-2 block">Model ID</span><input className="field" value={localModelId} onChange={(event) => setLocalModelId(event.target.value)} placeholder="qwen3.5-4b" /></label>
          {localModelError ? <p className="text-sm text-red-700">{localModelError}</p> : null}
          <div className="flex flex-wrap gap-2"><button type="button" className="primary-button" onClick={() => {
            const base_url = localBaseUrl.trim(); const model = localModelId.trim();
            if (!base_url || !model || !/^https?:\/\//i.test(base_url)) { setLocalModelError("请输入以 http:// 或 https:// 开头的 Base URL 和 Model ID。"); return; }
            saveLocalModel({ enabled: true, base_url, model }); setLocalModelError(null); setLocalModelOpen(false);
          }}>保存并启用</button><button type="button" className="secondary-button" onClick={restoreDefaultModel}>恢复默认模型</button></div>
        </div> : null}
      </section>

      <section className="panel p-5 lg:p-6">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {details.map(({ label, value, icon: Icon }) => (
            <div key={label} className="border-l-2 border-teal-500 bg-zinc-50 p-4">
              <Icon size={17} className="text-zinc-500" />
              <div className="mt-4 text-xs text-zinc-500">{label}</div>
              <div className="mt-1 break-words text-sm font-bold text-ink">{value}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5 lg:p-6">
        <h2 className="text-sm font-bold text-ink">{t("settings.providerEnvironment")}</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-600">{t("settings.providerHelp")}</p>
        <pre className="mt-5 overflow-x-auto rounded-md bg-zinc-950 p-4 text-xs leading-6 text-zinc-100">
          <code>{`LLM_PROVIDER=openai_compatible\nOPENAI_API_KEY=\nOPENAI_BASE_URL=https://api.openai.com/v1\nOPENAI_MODEL=gpt-4.1-mini\nLLM_TIMEOUT_SECONDS=45`}</code>
        </pre>
      </section>

      <section className="panel p-5 lg:p-6">
        <div className="flex flex-wrap items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-teal-50 text-teal-700">
            <KeyRound size={18} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-bold text-ink">{t("settings.deepseekTitle")}</h2>
              <span
                className={`rounded px-2 py-0.5 text-xs font-semibold ${
                  hasDeepseekApiKey
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-zinc-100 text-zinc-600"
                }`}
              >
                {hasDeepseekApiKey
                  ? t("settings.deepseekActive")
                  : t("settings.deepseekInactive")}
              </span>
            </div>
            <p className="mt-1 text-sm leading-6 text-zinc-600">
              {t("settings.deepseekDescription")}
            </p>
          </div>
        </div>

        <label className="mt-5 block" htmlFor="temporary-deepseek-key">
          <span className="label mb-2 block">{t("settings.deepseekLabel")}</span>
          <div className="flex items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <input
                id="temporary-deepseek-key"
                className="field pr-11"
                type={showKey ? "text" : "password"}
                value={deepseekApiKey}
                maxLength={512}
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                placeholder={t("settings.deepseekPlaceholder")}
                data-1p-ignore="true"
                data-lpignore="true"
                onChange={(event) => setDeepseekApiKey(event.target.value)}
              />
              <button
                type="button"
                className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-100 hover:text-ink"
                title={showKey ? t("settings.deepseekHide") : t("settings.deepseekShow")}
                aria-label={showKey ? t("settings.deepseekHide") : t("settings.deepseekShow")}
                onClick={() => setShowKey((current) => !current)}
              >
                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <button
              type="button"
              className="icon-button shrink-0 text-red-600"
              disabled={!hasDeepseekApiKey}
              title={t("settings.deepseekClear")}
              aria-label={t("settings.deepseekClear")}
              onClick={clearDeepseekApiKey}
            >
              <Trash2 size={16} />
            </button>
          </div>
        </label>

        <div className="mt-4 flex items-start gap-2 border-t border-zinc-100 pt-4 text-xs leading-5 text-zinc-500">
          <ShieldCheck className="mt-0.5 shrink-0 text-emerald-600" size={15} />
          <p>
            {t("settings.deepseekMemoryOnly")} {t("settings.deepseekTransport")}
          </p>
        </div>
      </section>

      <section className="panel p-5 lg:p-6">
        <h2 className="text-sm font-bold text-ink">{t("settings.publicLimits")}</h2>
        <dl className="mt-4 grid gap-4 sm:grid-cols-3">
          <div>
            <dt className="text-xs text-zinc-500">{t("settings.uploadBytes")}</dt>
            <dd className="mt-1 text-sm font-semibold text-ink">
              {(settings.upload_limits.max_bytes / 1024 / 1024).toFixed(0)} MB
            </dd>
          </div>
          <div>
            <dt className="text-xs text-zinc-500">{t("settings.uploadRows")}</dt>
            <dd className="mt-1 text-sm font-semibold text-ink">
              {formatNumber(settings.upload_limits.max_rows)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-zinc-500">{t("settings.uploadColumns")}</dt>
            <dd className="mt-1 text-sm font-semibold text-ink">
              {settings.upload_limits.max_columns}
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
