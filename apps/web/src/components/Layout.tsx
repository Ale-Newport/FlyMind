import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { STATIC_DEMO, api } from "../lib/api";
import { DatasetPicker, StaticNotice, useInterval } from "./ui";

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
  const color = STATIC_DEMO ? "bg-sky-400" : ok ? "bg-emerald-400" : ok === null ? "bg-ink-400" : "bg-rose-500";
  return (
    <span className="flex items-center gap-1.5 text-xs text-ink-400" data-testid="backend-status" title={ok === false ? "Start it with `make dev` or `uv run flymind serve`" : undefined}>
      <span className={`h-2 w-2 rounded-full ${color}`} /> {label}
    </span>
  );
}

export function Layout() {
  const navigate = useNavigate();
  const [help, setHelp] = useState(false);
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
  return (
    <div className="flex h-full flex-col">
      <StaticNotice />
      <header className="flex items-center gap-4 border-b border-ink-800 bg-ink-900/90 px-4 py-2">
        <NavLink to="/" className="flex items-center gap-2 font-semibold tracking-tight text-ink-100">
          <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" className="h-6 w-6" />
          FlyMind
        </NavLink>
        <nav aria-label="Main" className="flex flex-1 flex-wrap gap-1">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} title={`Alt+${n.key}`}
              className={({ isActive }) => `rounded-md px-2.5 py-1 text-sm transition ${isActive ? "bg-ink-700 text-accent" : "text-ink-300 hover:bg-ink-800 hover:text-ink-100"}`}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="w-64"><DatasetPicker compact /></div>
        <BackendStatus />
        <button className="btn px-2 py-0.5 text-xs" aria-label="Keyboard shortcuts" onClick={() => setHelp(true)}>?</button>
      </header>
      <main className="min-h-0 flex-1 overflow-auto">
        <Outlet />
      </main>
      {help && (
        <div role="dialog" aria-label="Keyboard shortcuts" className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setHelp(false)}>
          <div className="panel w-96 p-4 text-sm" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-2 font-semibold">Keyboard shortcuts</h2>
            <ul className="space-y-1 text-ink-300">
              {NAV.map((n) => <li key={n.key}><kbd className="mono rounded bg-ink-800 px-1">Alt+{n.key}</kbd> {n.label}</li>)}
              <li><kbd className="mono rounded bg-ink-800 px-1">Space</kbd> Simulator / Virtual Fly: start, pause, resume</li>
              <li><kbd className="mono rounded bg-ink-800 px-1">R</kbd> Explorer: reset camera</li>
              <li><kbd className="mono rounded bg-ink-800 px-1">?</kbd> toggle this help</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
