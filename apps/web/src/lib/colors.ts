// Consistent categorical colours across every view (explorer, plots, legends), per colour theme.
//
// Every function that returns a colour takes an optional `theme` ("dark" by default, which keeps the
// original values). Components should obtain the current theme from `useTheme()` /
// `useChartColors()` so views re-render when the user switches theme.
import { useMemo } from "react";
import { type ResolvedTheme, useTheme } from "./theme";

export type { ResolvedTheme } from "./theme";
export { useTheme } from "./theme";

// Chosen palette: warm, slightly desaturated hues with matched lightness per theme, so that categories
// read as one family on a charcoal or paper ground (not as default web colours).
export const NT_COLORS: Record<string, string> = {
  ACH: "#6fbf7f",
  GABA: "#e5654f",
  GLUT: "#6c9bd2",
  DA: "#e89a4a",
  SER: "#b494dc",
  OCT: "#e0c040",
  HIST: "#4fc3b0",
  UNKNOWN: "#6a655b",
  unknown: "#6a655b",
};

export const SUPER_CLASS_COLORS: Record<string, string> = {
  optic: "#6c9bd2",
  central: "#a39e92",
  sensory: "#7fc47a",
  visual_projection: "#8f8ce0",
  ascending: "#e0a540",
  descending: "#e57f9a",
  visual_centrifugal: "#b494dc",
  motor: "#e5654f",
  endocrine: "#b5c24a",
  unknown: "#6a655b",
};

export const SIDE_COLORS: Record<string, string> = {
  left: "#6c9bd2",
  right: "#e57f9a",
  center: "#e0a540",
  na: "#6a655b",
  unknown: "#6a655b",
};

// Light-ground variants: same hues, lower lightness so points and lines stay visible on warm paper.
const NT_COLORS_LIGHT: Record<string, string> = {
  ACH: "#2f7d44", GABA: "#b3402d", GLUT: "#2f5f9e", DA: "#b0580a", SER: "#6b4a9c", OCT: "#8a7000", HIST: "#0e7c70",
  UNKNOWN: "#a09a8c", unknown: "#a09a8c",
};
const SUPER_CLASS_COLORS_LIGHT: Record<string, string> = {
  optic: "#2f5f9e", central: "#7d786c", sensory: "#3b7a3e", visual_projection: "#4f4cb0", ascending: "#9a6a00",
  descending: "#b02f58", visual_centrifugal: "#6b4a9c", motor: "#b3402d", endocrine: "#6f7a10", unknown: "#a09a8c",
};
const SIDE_COLORS_LIGHT: Record<string, string> = {
  left: "#2f5f9e", right: "#b02f58", center: "#9a6a00", na: "#a09a8c", unknown: "#a09a8c",
};

/** OKLCH -> sRGB hex (gamut-clamped). Used to build the many-category palette systematically. */
function oklch(L: number, C: number, hDeg: number): string {
  const h = (hDeg * Math.PI) / 180;
  const a = C * Math.cos(h), b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s];
  return "#" + lin.map((v) => {
    const c = Math.max(0, Math.min(1, v));
    const g = c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
    return Math.round(g * 255).toString(16).padStart(2, "0");
  }).join("");
}

// 30 categories: hue steps of the golden angle, lightness alternating across three levels so that
// neighbours in hue are still separable. Index-aligned between themes.
const PALETTE = Array.from({ length: 30 }, (_, i) => oklch([0.76, 0.68, 0.83][i % 3], 0.115, (i * 137.508 + 28) % 360));
// Light: every entry has >= 3:1 contrast against white and against the paper tone (they are marks, not text).
const PALETTE_LIGHT = Array.from({ length: 30 }, (_, i) => oklch([0.52, 0.58, 0.46][i % 3], 0.125, (i * 137.508 + 28) % 360));

const UNLABELLED_DARK = "#6a655b";
const UNLABELLED_LIGHT = "#a09a8c";

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
  /** second data colour (ochre) */
  accent2: string;
  /** neutral series (baselines, "before" snapshots) */
  neutral: string;
  /** secondary text (legends) */
  text: string;
  textStrong: string;
  /** tick labels and axis titles */
  textMuted: string;
  grid: string;
  zeroline: string;
  axisLine: string;
  /** Plotly paper / plot backgrounds (transparent so the page shows through) */
  paper: string;
  plot: string;
  hoverBg: string;
  hoverBorder: string;
  hoverText: string;
  /** categorical palette valid on the current background (first entry = accent) */
  palette: string[];
  fontFamily: string;
  monoFamily: string;
  scene: SceneColors;
  /** deterministic colour for an arbitrary label */
  cat: (label: string) => string;
  /** categoryColor bound to this theme */
  category: (field: string, label: string) => string;
  /** rateColor bound to this theme */
  rate: (t: number) => RGB;
}

const FONT = '"Geist Variable", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
const MONO = '"Geist Mono Variable", ui-monospace, SFMono-Regular, Menlo, monospace';

const DARK_BASE = {
  accent: "#5eead4", accent2: "#dcaa52", neutral: "#8d877b",
  text: "#bdb7aa", textStrong: "#ece8df", textMuted: "#958f83",
  grid: "#272521", zeroline: "#403d37", axisLine: "#403d37",
  hoverBg: "#24221e", hoverBorder: "#403d37", hoverText: "#ece8df",
  palette: ["#5eead4", "#dcaa52", "#86a8d6", "#e5806f", "#b595d9", "#8fc48b", "#e07fa0", "#b9b46a"],
  scene: {
    bg: "#121110", inactive: [0.3, 0.29, 0.27], selected: [0.98, 0.96, 0.9], highlight: [0.95, 0.75, 0.25],
    upstream: [0.42, 0.68, 1.0], downstream: [1.0, 0.45, 0.58], fallback: [0.42, 0.4, 0.37], skeleton: "#f4efe4",
    axis: { x: "#e5654f", y: "#6fbf7f", z: "#6c9bd2" }, grid: "#2a2824", additiveOk: true,
  } satisfies SceneColors,
};
const LIGHT_BASE = {
  accent: "#0b6b63", accent2: "#9a6a00", neutral: "#8c8676",
  text: "#423e36", textStrong: "#1b1915", textMuted: "#67625a",
  grid: "#e4dfd2", zeroline: "#c9c2b1", axisLine: "#c9c2b1",
  hoverBg: "#fbf9f4", hoverBorder: "#8c8676", hoverText: "#1b1915",
  palette: ["#0b6b63", "#9a6a00", "#2f5f9e", "#b3402d", "#6b4a9c", "#3b7a3e", "#b02f58", "#6f6a10"],
  scene: {
    bg: "#f1ede3", inactive: [0.62, 0.6, 0.55], selected: [0.1, 0.09, 0.08], highlight: [0.8, 0.45, 0.0],
    upstream: [0.1, 0.38, 0.78], downstream: [0.78, 0.15, 0.35], fallback: [0.55, 0.53, 0.48], skeleton: "#1b1915",
    axis: { x: "#b3402d", y: "#2f7d44", z: "#2f5f9e" }, grid: "#ddd7c9", additiveOk: false,
  } satisfies SceneColors,
};

export function chartColors(theme: ResolvedTheme): ChartColors {
  const b = theme === "light" ? LIGHT_BASE : DARK_BASE;
  return {
    theme, ...b, paper: "rgba(0,0,0,0)", plot: "rgba(0,0,0,0)", fontFamily: FONT, monoFamily: MONO,
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

/** CSS colour string for an rgb triple in 0..1. */
export const rgbCss = (c: RGB) => `rgb(${Math.round(c[0] * 255)} ${Math.round(c[1] * 255)} ${Math.round(c[2] * 255)})`;
