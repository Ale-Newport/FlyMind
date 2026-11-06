import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { STATIC_DEMO, api } from "../lib/api";
import { DatasetPicker, StaticNotice, useInterval } from "./ui";
import { ThemeToggle } from "./ThemeToggle";
import { Brand } from "./Brand";
import { Icon } from "./Icon";

export const NAV = [
  { to: "/", label: "Overview", key: "1" },
  { to: "/explorer", label: "Brain explorer", key: "2" },
  { to: "/simulator", label: "Brain simulator", key: "3" },
  { to: "/fly", label: "Virtual fly", key: "4" },
  { to: "/experiments", label: "Experiments", key: "5" },
  { to: "/datasets", label: "Datasets", key: "6" },
  { to: "/docs", label: "Documentation", key: "7" },
];

function BackendStatus() {
  const [ok, setOk] = useState<boolean | null>(null);
  const check = () => api.health().then(() => setOk(true), () => setOk(false));
  useEffect(() => { check(); }, []);
  useInterval(check, 10_000);
  const label = STATIC_DEMO ? "static demo" : ok === null ? "checking" : ok ? "backend online" : "backend offline";
  const color = STATIC_DEMO ? "var(--info)" : ok ? "var(--ok)" : ok === null ? "var(--ink-4)" : "var(--danger)";
  return (
    <span className="flex items-center gap-2 whitespace-nowrap" data-testid="backend-status" role="status"
      title={ok === false ? "Start it with `make dev` or `uv run flymind serve`" : label}>
      <span aria-hidden className="h-[7px] w-[7px] shrink-0" style={{ background: color }} />
      {label}
    </span>
  );
}

const SHORTCUTS: [string, string][] = [
  ["Space", "Simulator and Virtual fly: start, pause, resume"],
  ["F", "Virtual fly: switch between walking and flight"],
  ["R", "Brain explorer: reset the camera"],
  ["?", "Show or hide this list"],
];

export function Layout() {
  const navigate = useNavigate();
  const [help, setHelp] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      if (e.altKey && /^[1-7]$/.test(e.key)) {
        const item = NAV.find((n) => n.key === e.key);
        if (item) { e.preventDefault(); navigate(item.to); }
      }
      if (e.key === "?") setHelp((h) => !h);
      if (e.key === "Escape") setHelp(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);
  useEffect(() => { if (help) closeRef.current?.focus(); }, [help]);
  return (
    <div className="flex h-full flex-col">
      {/* HashRouter owns location.hash, so the skip link focuses <main> instead of using an anchor */}
      <button type="button" className="skip-link" onClick={() => mainRef.current?.focus()}>Skip to content</button>
      <StaticNotice />
      <header className="masthead shrink-0">
        <div className="mx-auto flex max-w-[1920px] flex-wrap items-center gap-x-8 px-5 xl:flex-nowrap">
          <div className="flex h-[var(--header-h)] items-center"><Brand /></div>
          <nav aria-label="Main" className="order-3 -mx-2 flex w-full overflow-x-auto px-0 xl:order-none xl:mx-0 xl:w-auto xl:flex-1 xl:overflow-visible">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"} title={`Alt+${n.key}`} className="nav-link">
                <span className="n hidden min-[1440px]:inline" aria-hidden>{n.key}</span>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 py-2 xl:ml-0">
            <div className="w-48 min-[1440px]:w-60"><DatasetPicker compact /></div>
            <ThemeToggle />
            <button className="btn btn-icon btn-quiet" aria-label="Keyboard shortcuts" data-tip="Keyboard shortcuts (?)" data-tip-align="end" onClick={() => setHelp(true)}>
              <Icon name="keyboard" />
            </button>
          </div>
        </div>
      </header>
      <main id="main" ref={mainRef} tabIndex={-1} className="min-h-0 flex-1 overflow-auto outline-none">
        <Outlet />
      </main>
      <footer className="statusbar shrink-0">
        <div className="mx-auto flex max-w-[1920px] items-center justify-between gap-4 px-5 py-1">
          <BackendStatus />
          <span className="hidden sm:inline">Alt+1 to Alt+7 switch pages</span>
        </div>
      </footer>
      {help && (
        <div role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" className="fixed inset-0 z-50 flex items-center justify-center bg-(--scrim) p-4" onClick={() => setHelp(false)}>
          <div className="w-full max-w-md border border-rule-strong bg-paper p-6 text-sm" style={{ boxShadow: "var(--shadow-pop)", borderRadius: 3 }} onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-baseline justify-between">
              <h2 className="t-head">Keyboard shortcuts</h2>
              <button ref={closeRef} className="btn btn-icon btn-quiet btn-sm" onClick={() => setHelp(false)} aria-label="Close shortcuts"><Icon name="close" size={14} /></button>
            </div>
            <ul className="kv">
              {NAV.map((n) => <li key={n.key} className="flex items-baseline gap-4 border-b border-rule py-1.5"><kbd className="w-14 shrink-0 text-center">Alt+{n.key}</kbd><span className="text-ink-2">{n.label}</span></li>)}
              {SHORTCUTS.map(([k, d]) => <li key={k} className="flex items-baseline gap-4 border-b border-rule py-1.5 last:border-b-0"><kbd className="w-14 shrink-0 text-center">{k}</kbd><span className="text-ink-2">{d}</span></li>)}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
