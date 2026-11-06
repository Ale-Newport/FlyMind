// Consistent categorical colours across every view (explorer, plots, legends), per colour theme.
//
// Every function that returns a colour takes an optional `theme` ("dark" by default, which keeps the
// original values). Components should obtain the current theme from `useTheme()` /
// `useChartColors()` so views re-render when the user switches theme.
import { useMemo } from "react";
import { type ResolvedTheme, useTheme } from "./theme";

export type { ResolvedTheme } from "./theme";
export { useTheme } from "./theme";

export const NT_COLORS: Record<string, string> = {
  ACH: "#34d399",
  GABA: "#f43f5e",
  GLUT: "#60a5fa",
  DA: "#fb923c",
  SER: "#c084fc",
  OCT: "#facc15",
  HIST: "#2dd4bf",
  UNKNOWN: "#64748b",
  unknown: "#64748b",
};

export const SUPER_CLASS_COLORS: Record<string, string> = {
  optic: "#3b82f6",
  central: "#a3a3a3",
  sensory: "#22d3ee",
  visual_projection: "#818cf8",
  ascending: "#f59e0b",
  descending: "#f472b6",
  visual_centrifugal: "#a78bfa",
  motor: "#ef4444",
  endocrine: "#84cc16",
  unknown: "#475569",
};

export const SIDE_COLORS: Record<string, string> = {
  left: "#38bdf8",
  right: "#fb7185",
  center: "#facc15",
  na: "#64748b",
  unknown: "#64748b",
};

// Light-background variants: same hues, lower lightness so points and lines stay visible on white.
const NT_COLORS_LIGHT: Record<string, string> = {
  ACH: "#059669", GABA: "#e11d48", GLUT: "#2563eb", DA: "#ea580c", SER: "#9333ea", OCT: "#a16207", HIST: "#0d9488",
  UNKNOWN: "#94a3b8", unknown: "#94a3b8",
};
const SUPER_CLASS_COLORS_LIGHT: Record<string, string> = {
  optic: "#2563eb", central: "#737373", sensory: "#0891b2", visual_projection: "#4f46e5", ascending: "#d97706",
  descending: "#db2777", visual_centrifugal: "#7c3aed", motor: "#dc2626", endocrine: "#65a30d", unknown: "#94a3b8",
};
const SIDE_COLORS_LIGHT: Record<string, string> = {
  left: "#0284c7", right: "#e11d48", center: "#a16207", na: "#94a3b8", unknown: "#94a3b8",
};

// Glasbey-like high-contrast palette for many categories (neuropils, cell types).
const PALETTE = [
  "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6",
  "#bcf60c", "#fabebe", "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000", "#aaffc3",
  "#808000", "#ffd8b1", "#5b8cff", "#ff6f91", "#00c2a8", "#ffa600", "#7a5195", "#58ff8a",
  "#ff4d4d", "#4dd2ff", "#c9a227", "#9d4edd", "#2ec4b6", "#ff9f1c",
];
// Index-aligned with PALETTE; every entry has >= 2.4:1 contrast against white (they are marks, not text).
const PALETTE_LIGHT = [
  "#d1103f", "#2a9d3a", "#b89400", "#3250c0", "#e0650f", "#7e17a0", "#0e9aa7", "#c91fc0",
  "#6f9400", "#d9728a", "#006b6b", "#a064d6", "#8a5319", "#a09230", "#7a0a0a", "#3fb87a",
  "#6d6d00", "#d9944f", "#3d6fe6", "#e04a73", "#00907e", "#d98400", "#6a4285", "#23a85a",
  "#d93030", "#0891c4", "#a8851a", "#8a3bc9", "#1a9c90", "#e07f00",
];

const UNLABELLED_DARK = "#475569";
const UNLABELLED_LIGHT = "#94a3b8";

export function hashColor(label: string, theme: ResolvedTheme = "dark"): string {
  let h = 2166136261;
  for (let i = 0; i < label.length; i++) {
    h ^= label.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (theme === "light" ? PALETTE_LIGHT : PALETTE)[Math.abs(h) % PALETTE.length];
}

export function categoryColor(field: string, label: string, theme: ResolvedTheme = "dark"): string {
  const light = theme === "light";
  if (field === "nt_type") { const m = light ? NT_COLORS_LIGHT : NT_COLORS; return m[label] ?? m.UNKNOWN; }
  if (field === "super_class") return (light ? SUPER_CLASS_COLORS_LIGHT : SUPER_CLASS_COLORS)[label] ?? hashColor(label, theme);
  if (field === "side") { const m = light ? SIDE_COLORS_LIGHT : SIDE_COLORS; return m[label] ?? m.unknown; }
  if (label === "unknown" || label === "unannotated" || label === "other") return light ? UNLABELLED_LIGHT : UNLABELLED_DARK;
  return hashColor(label, theme);
}

export function hexToRgb(hex: string): [number, number, number] {
  const v = parseInt(hex.slice(1), 16);
  return [((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255];
}

type RGB = [number, number, number];

const RATE_STOPS_DARK: RGB[] = [[0.12, 0.05, 0.25], [0.55, 0.1, 0.45], [0.9, 0.3, 0.2], [0.99, 0.75, 0.2], [1.0, 1.0, 0.85]];
// On a light background the ramp runs from pale warm to deep purple (high rate = darkest, most salient).
const RATE_STOPS_LIGHT: RGB[] = [[0.99, 0.82, 0.4], [0.96, 0.5, 0.2], [0.8, 0.15, 0.3], [0.45, 0.06, 0.4], [0.1, 0.02, 0.22]];

/** Perceptual-ish "inferno"-like ramp for firing rates in [0, 1] (reversed lightness on light backgrounds). */
export function rateColor(t: number, theme: ResolvedTheme = "dark"): RGB {
  const x = Math.max(0, Math.min(1, t));
  const stops = theme === "light" ? RATE_STOPS_LIGHT : RATE_STOPS_DARK;
  const s = x * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(s));
  const f = s - i;
  return [0, 1, 2].map((k) => stops[i][k] * (1 - f) + stops[i + 1][k] * f) as RGB;
}

// ------------------------------------------------------------------ chart + 3D theme colours
// These mirror the CSS variables in index.css (single source for canvas/Plotly code, which cannot
// read CSS variables).
export interface SceneColors {
  /** WebGL clear colour */
  bg: string;
  /** rgb (0..1) of non-active points when colouring by activity */
  inactive: RGB;
  /** rgb of the selected neuron / highlighted pathway / upstream / downstream partners */
  selected: RGB;
  highlight: RGB;
  upstream: RGB;
  downstream: RGB;
  /** rgb for a point whose category is unknown */
  fallback: RGB;
  /** skeleton line colour (CSS colour) */
  skeleton: string;
  /** orientation gizmo axis colours */
  axis: { x: string; y: string; z: string };
  /** ground / grid / secondary line colours for 3D scenes */
  grid: string;
  /** whether additive blending is appropriate (only on dark backgrounds) */
  additiveOk: boolean;
}

export interface ChartColors {
  theme: ResolvedTheme;
  accent: string;
  accent2: string;
  /** neutral series (baselines, "before" snapshots) */
  neutral: string;
  text: string;
  textStrong: string;
  textMuted: string;
  grid: string;
  zeroline: string;
  axisLine: string;
  /** Plotly paper / plot backgrounds (transparent so panels show through) */
  paper: string;
  plot: string;
  hoverBg: string;
  hoverBorder: string;
  hoverText: string;
  /** categorical palette valid on the current background (first entries = accent family) */
  palette: string[];
  fontFamily: string;
  scene: SceneColors;
  /** deterministic colour for an arbitrary label */
  cat: (label: string) => string;
  /** categoryColor bound to this theme */
  category: (field: string, label: string) => string;
  /** rateColor bound to this theme */
  rate: (t: number) => RGB;
}

const FONT = '"Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';

const DARK_BASE = {
  accent: "#5eead4", accent2: "#f472b6", neutral: "#64748b",
  text: "#aab4c8", textStrong: "#e8ecf5", textMuted: "#8591a8",
  grid: "#1c2333", zeroline: "#2d3750", axisLine: "#2d3750",
  hoverBg: "#181e2b", hoverBorder: "#3a4560", hoverText: "#e8ecf5",
  palette: ["#5eead4", "#f472b6", "#60a5fa", "#fbbf24", "#a78bfa", "#fb923c", "#34d399", "#f87171"],
  scene: {
    bg: "#080b12", inactive: [0.22, 0.22, 0.22], selected: [1, 1, 1], highlight: [1, 0.85, 0.2],
    upstream: [0.25, 0.85, 1.0], downstream: [1.0, 0.35, 0.7], fallback: [0.4, 0.4, 0.5], skeleton: "#f8fafc",
    axis: { x: "#fb7185", y: "#34d399", z: "#60a5fa" }, grid: "#232b3c", additiveOk: true,
  } satisfies SceneColors,
};
const LIGHT_BASE = {
  accent: "#0f766e", accent2: "#db2777", neutral: "#64748b",
  text: "#3b4558", textStrong: "#0e1523", textMuted: "#596377",
  grid: "#e4e8ef", zeroline: "#c3cad6", axisLine: "#c3cad6",
  hoverBg: "#ffffff", hoverBorder: "#98a2b3", hoverText: "#0e1523",
  palette: ["#0f766e", "#db2777", "#2563eb", "#d97706", "#7c3aed", "#ea580c", "#059669", "#dc2626"],
  scene: {
    bg: "#f5f6f8", inactive: [0.5, 0.55, 0.65], selected: [0.05, 0.08, 0.14], highlight: [0.9, 0.45, 0.0],
    upstream: [0.0, 0.5, 0.75], downstream: [0.85, 0.1, 0.5], fallback: [0.5, 0.52, 0.6], skeleton: "#0e1523",
    axis: { x: "#be123c", y: "#047857", z: "#1d4ed8" }, grid: "#dce1e9", additiveOk: false,
  } satisfies SceneColors,
};

export function chartColors(theme: ResolvedTheme): ChartColors {
  const b = theme === "light" ? LIGHT_BASE : DARK_BASE;
  return {
    theme, ...b, paper: "rgba(0,0,0,0)", plot: "rgba(0,0,0,0)", fontFamily: FONT,
    cat: (label) => hashColor(label, theme),
    category: (field, label) => categoryColor(field, label, theme),
    rate: (t) => rateColor(t, theme),
  };
}

/** Theme-aware colours for Plotly charts and three.js scenes; re-renders when the theme changes. */
export function useChartColors(): ChartColors {
  const { resolved } = useTheme();
  return useMemo(() => chartColors(resolved), [resolved]);
}

/** Dark-theme Plotly layout defaults. Prefer `useChartColors()` (Plot does this for you). */
export const PLOT_LAYOUT_BASE = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#aab4c8", size: 11, family: FONT },
  margin: { l: 48, r: 12, t: 24, b: 36 },
  xaxis: { gridcolor: "#1c2333", zerolinecolor: "#2d3750" },
  yaxis: { gridcolor: "#1c2333", zerolinecolor: "#2d3750" },
  legend: { orientation: "h" as const, y: -0.25 },
};
