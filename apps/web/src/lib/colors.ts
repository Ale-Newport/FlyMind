// Consistent categorical colours across every view (explorer, plots, legends).

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

// Glasbey-like high-contrast palette for many categories (neuropils, cell types).
const PALETTE = [
  "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6",
  "#bcf60c", "#fabebe", "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000", "#aaffc3",
  "#808000", "#ffd8b1", "#5b8cff", "#ff6f91", "#00c2a8", "#ffa600", "#7a5195", "#58ff8a",
  "#ff4d4d", "#4dd2ff", "#c9a227", "#9d4edd", "#2ec4b6", "#ff9f1c",
];

export function hashColor(label: string): string {
  let h = 2166136261;
  for (let i = 0; i < label.length; i++) {
    h ^= label.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return PALETTE[Math.abs(h) % PALETTE.length];
}

export function categoryColor(field: string, label: string): string {
  if (field === "nt_type") return NT_COLORS[label] ?? NT_COLORS.UNKNOWN;
  if (field === "super_class") return SUPER_CLASS_COLORS[label] ?? hashColor(label);
  if (field === "side") return SIDE_COLORS[label] ?? SIDE_COLORS.unknown;
  if (label === "unknown" || label === "unannotated" || label === "other") return "#475569";
  return hashColor(label);
}

export function hexToRgb(hex: string): [number, number, number] {
  const v = parseInt(hex.slice(1), 16);
  return [((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255];
}

/** Perceptual-ish "inferno"-like ramp for firing rates in [0, 1]. */
export function rateColor(t: number): [number, number, number] {
  const x = Math.max(0, Math.min(1, t));
  const stops: [number, number, number][] = [
    [0.12, 0.05, 0.25], [0.55, 0.1, 0.45], [0.9, 0.3, 0.2], [0.99, 0.75, 0.2], [1.0, 1.0, 0.85],
  ];
  const s = x * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(s));
  const f = s - i;
  return [0, 1, 2].map((k) => stops[i][k] * (1 - f) + stops[i + 1][k] * f) as [number, number, number];
}

export const PLOT_LAYOUT_BASE = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#a7b0c8", size: 11, family: "Inter, system-ui, sans-serif" },
  margin: { l: 48, r: 12, t: 24, b: 36 },
  xaxis: { gridcolor: "#1f2944", zerolinecolor: "#2c3859" },
  yaxis: { gridcolor: "#1f2944", zerolinecolor: "#2c3859" },
  legend: { orientation: "h" as const, y: -0.25 },
};
