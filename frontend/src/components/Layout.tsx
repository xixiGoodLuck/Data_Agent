import {
  Activity,
  Database,
  FlaskConical,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  MessagesSquare,
  ScrollText,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useI18n } from "../i18n";
import { useTemporaryCredentials } from "../temporaryCredentials";

const navigation = [
  { to: "/", label: "nav.dashboard", icon: LayoutDashboard },
  { to: "/ask", label: "nav.ask", icon: MessageSquareText },
  { to: "/datasets", label: "nav.datasets", icon: Database },
  { to: "/conversations", label: "nav.conversations", icon: MessagesSquare },
  { to: "/logs", label: "nav.logs", icon: ScrollText },
  { to: "/approvals", label: "nav.approvals", icon: ShieldCheck },
  { to: "/evals", label: "nav.evals", icon: FlaskConical },
  { to: "/settings", label: "nav.settings", icon: Settings },
] as const;

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useI18n();
  const { hasDeepseekApiKey, localModel } = useTemporaryCredentials();
  const modelStatus = localModel.enabled
    ? t("layout.localReady", { model: localModel.model })
    : hasDeepseekApiKey
      ? t("layout.deepseekReady")
      : t("layout.mockReady");
  return (
    <div className="flex h-full flex-col bg-ink text-white">
      <div className="flex h-16 items-center gap-3 border-b border-white/10 px-5">
        <span className="flex h-9 w-9 items-center justify-center rounded-md bg-teal-500 text-white">
          <Activity size={20} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-bold">InsightOps Agent</div>
          <div className="text-xs text-zinc-400">{t("layout.subtitle")}</div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4" aria-label={t("layout.primaryNavigation")}>
        {navigation.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition ${
                isActive
                  ? "bg-white text-ink"
                  : "text-zinc-300 hover:bg-white/10 hover:text-white"
              }`
            }
          >
            <Icon size={18} aria-hidden="true" />
            {t(label)}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-white/10 px-5 py-4 text-xs text-zinc-400">
        <span className="status-dot mr-2 bg-emerald-400" />
        {modelStatus}
      </div>
    </div>
  );
}

export function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const { language, setLanguage, t } = useI18n();
  const titleKey = navigation.find((item) => item.to === location.pathname)?.label;
  const title = titleKey ? t(titleKey) : "InsightOps Agent";

  return (
    <div className="min-h-screen bg-canvas lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] lg:block">
        <Sidebar />
      </aside>
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-black/40"
            aria-label={t("layout.closeNavigation")}
            onClick={() => setMobileOpen(false)}
          />
          <aside className="relative h-full w-[280px] shadow-2xl">
            <button
              className="absolute right-3 top-3 z-10 flex h-9 w-9 items-center justify-center rounded-md text-zinc-300 hover:bg-white/10"
              aria-label={t("layout.closeNavigation")}
              onClick={() => setMobileOpen(false)}
            >
              <X size={20} />
            </button>
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      ) : null}
      <div className="min-w-0 lg:col-start-2">
        <header className="sticky top-0 z-30 flex h-16 items-center border-b border-zinc-200 bg-white/95 px-4 backdrop-blur lg:px-8">
          <button
            className="icon-button mr-3 lg:hidden"
            aria-label={t("layout.openNavigation")}
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={20} />
          </button>
          <h1 className="text-lg font-bold text-ink">{title}</h1>
          <div className="ml-auto flex items-center gap-3">
            <div className="flex h-8 items-center rounded-md border border-zinc-200 bg-zinc-50 p-0.5" role="group" aria-label={t("language.switch")}>
              {(["zh", "en"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  className={`h-7 min-w-10 rounded px-2 text-xs font-semibold transition ${language === option ? "bg-white text-ink shadow-sm" : "text-zinc-500 hover:text-ink"}`}
                  aria-pressed={language === option}
                  onClick={() => setLanguage(option)}
                >
                  {t(`language.${option}`)}
                </button>
              ))}
            </div>
            <div className="hidden items-center gap-2 text-xs text-zinc-500 sm:flex">
              <span className="status-dot bg-emerald-500" /> {t("layout.apiConnected")}
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1600px] p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
