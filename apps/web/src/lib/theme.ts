// Colour-theme state: user preference ("system" | "light" | "dark") + the resolved theme.
//
// The preference is persisted under its own localStorage key (NOT inside `flymind-prefs`) and is
// applied to <html data-theme="…"> before first paint by the inline script in index.html.
// This module keeps the attribute in sync afterwards and follows the OS setting while the
// preference is "system".
import { create } from "zustand";

export type ThemePref = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "flymind-theme";

function readPref(): ThemePref {
  try {
    const v = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch { /* storage blocked: fall through */ }
  return "system";
}

function writePref(p: ThemePref) {
  try { window.localStorage.setItem(THEME_STORAGE_KEY, p); } catch { /* storage blocked */ }
}

function systemTheme(): ResolvedTheme {
  try {
    if (typeof window.matchMedia === "function") return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch { /* ignore */ }
  return "dark";
}

interface ThemeState {
  pref: ThemePref;
  system: ResolvedTheme;
  setPref: (p: ThemePref) => void;
}

export const useThemeStore = create<ThemeState>()((set) => ({
  pref: typeof window === "undefined" ? "system" : readPref(),
  system: typeof window === "undefined" ? "dark" : systemTheme(),
  setPref: (pref) => { writePref(pref); set({ pref }); },
}));

export const resolveTheme = (s: Pick<ThemeState, "pref" | "system">): ResolvedTheme => (s.pref === "system" ? s.system : s.pref);

/** Imperative read, for code outside React (e.g. an animation loop). */
export const getResolvedTheme = (): ResolvedTheme => resolveTheme(useThemeStore.getState());

function apply(theme: ResolvedTheme) {
  const root = document.documentElement;
  if (root.dataset.theme !== theme) root.dataset.theme = theme;
  root.style.colorScheme = theme;
}

if (typeof window !== "undefined") {
  apply(getResolvedTheme());
  useThemeStore.subscribe((s) => apply(resolveTheme(s)));
  try {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => useThemeStore.setState({ system: mq.matches ? "dark" : "light" });
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else (mq as MediaQueryList).addListener?.(onChange);
  } catch { /* matchMedia unavailable (tests) */ }
}

/** `{ pref, resolved, setPref }`: `resolved` is always "light" or "dark" and re-renders on change. */
export function useTheme(): { pref: ThemePref; resolved: ResolvedTheme; setPref: (p: ThemePref) => void } {
  const pref = useThemeStore((s) => s.pref);
  const system = useThemeStore((s) => s.system);
  const setPref = useThemeStore((s) => s.setPref);
  return { pref, resolved: pref === "system" ? system : pref, setPref };
}
