import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { STATIC_DEMO, api } from "../lib/api";
import { DatasetPicker, StaticNotice, useInterval } from "./ui";
import { ThemeToggle } from "./ThemeToggle";

export const NAV = [
  { to: "/", label: "Overview", key: "1" },
  { to: "/explorer", label: "Brain Explorer", key: "2" },
  { to: "/simulator", label: "Brain Simulator", key: "3" },
  { to: "/fly", label: "Virtual Fly", key: "4" },
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
  const color = STATIC_DEMO ? "bg-(--info)" : ok ? "bg-(--ok)" : ok === null ? "bg-ink-500" : "bg-(--danger)";
  return (
    <span className="flex items-center gap-2 whitespace-nowrap text-xs text-ink-300" data-testid="backend-status" role="status"
      title={ok === false ? "Start it with `make dev` or `uv run flymind serve`" : label}>
      <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${color} ${ok === null && !STATIC_DEMO ? "animate-pulse" : ""}`} />
      {/* label stays in the DOM (tests, screen readers); only visually collapsed on mid-width single-row headers */}
      <span className="xl:max-[1439px]:sr-only">{label}</span>
    </span>
  );
}

function Brand() {
  return (
    <NavLink to="/" aria-label="FlyMind home" className="-ml-1 flex items-center gap-2 rounded-md px-1 py-2 text-[15px] font-semibold tracking-tight text-ink-100 no-underline">
      <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" className="h-6 w-6 rounded-md" />
      <span>FlyMind</span>
    </NavLink>
  );
}

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
      <header className="app-header shrink-0">
        <div className="mx-auto flex max-w-[1920px] flex-wrap items-center gap-x-6 px-4 xl:flex-nowrap">
          <Brand />
          <nav aria-label="Main" className="order-3 -mx-1 flex w-full gap-0.5 overflow-x-auto px-1 xl:order-none xl:w-auto xl:flex-1 xl:overflow-visible">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"} title={`Alt+${n.key}`} className="nav-link">
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 py-1.5 xl:ml-0">
            <div className="w-52 xl:w-56"><DatasetPicker compact /></div>
            <BackendStatus />
            <ThemeToggle />
            <button className="btn !px-2 !py-1 text-xs" aria-label="Keyboard shortcuts" data-tip="Keyboard shortcuts (?)" data-tip-align="end" onClick={() => setHelp(true)}>?</button>
          </div>
        </div>
      </header>
      <main id="main" ref={mainRef} tabIndex={-1} className="min-h-0 flex-1 overflow-auto outline-none">
        <Outlet />
      </main>
      {help && (
        <div role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" className="fixed inset-0 z-50 flex items-center justify-center bg-(--scrim) p-4" onClick={() => setHelp(false)}>
          <div className="panel rise w-full max-w-sm p-5 text-sm" style={{ boxShadow: "var(--shadow-pop)" }} onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold">Keyboard shortcuts</h2>
              <button ref={closeRef} className="btn !px-2 !py-0.5 text-xs" onClick={() => setHelp(false)} aria-label="Close shortcuts">Esc</button>
            </div>
            <ul className="space-y-1.5 text-ink-300">
              {NAV.map((n) => <li key={n.key} className="flex items-center gap-3"><kbd className="w-14 text-center">Alt+{n.key}</kbd> {n.label}</li>)}
              <li className="flex items-center gap-3"><kbd className="w-14 text-center">Space</kbd> Simulator / Virtual Fly: start, pause, resume</li>
              <li className="flex items-center gap-3"><kbd className="w-14 text-center">R</kbd> Explorer: reset camera</li>
              <li className="flex items-center gap-3"><kbd className="w-14 text-center">?</kbd> toggle this help</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
