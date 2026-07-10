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

const navigation = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/ask", label: "Ask Data", icon: MessageSquareText },
  { to: "/datasets", label: "Datasets", icon: Database },
  { to: "/conversations", label: "Conversations", icon: MessagesSquare },
  { to: "/logs", label: "Query Logs", icon: ScrollText },
  { to: "/approvals", label: "Approvals", icon: ShieldCheck },
  { to: "/evals", label: "Eval Center", icon: FlaskConical },
  { to: "/settings", label: "Settings", icon: Settings },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-ink text-white">
      <div className="flex h-16 items-center gap-3 border-b border-white/10 px-5">
        <span className="flex h-9 w-9 items-center justify-center rounded-md bg-teal-500 text-white">
          <Activity size={20} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-bold">InsightOps Agent</div>
          <div className="text-xs text-zinc-400">Data operations console</div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4" aria-label="Primary navigation">
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
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-white/10 px-5 py-4 text-xs text-zinc-400">
        <span className="status-dot mr-2 bg-emerald-400" />
        Mock provider ready
      </div>
    </div>
  );
}

export function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const title = navigation.find((item) => item.to === location.pathname)?.label ?? "InsightOps Agent";

  return (
    <div className="min-h-screen bg-canvas lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] lg:block">
        <Sidebar />
      </aside>
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-black/40"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="relative h-full w-[280px] shadow-2xl">
            <button
              className="absolute right-3 top-3 z-10 flex h-9 w-9 items-center justify-center rounded-md text-zinc-300 hover:bg-white/10"
              aria-label="Close navigation"
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
            aria-label="Open navigation"
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={20} />
          </button>
          <h1 className="text-lg font-bold text-ink">{title}</h1>
          <div className="ml-auto flex items-center gap-2 text-xs text-zinc-500">
            <span className="status-dot bg-emerald-500" /> API connected
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1600px] p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
