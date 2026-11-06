import { useEffect, useMemo, useRef } from "react";
import type { Data, Layout } from "plotly.js-dist-min";
import { type ChartColors, useChartColors } from "../lib/colors";

type PlotlyModule = typeof import("plotly.js-dist-min");
let plotlyPromise: Promise<PlotlyModule> | null = null;
const loadPlotly = () => (plotlyPromise ??= import("plotly.js-dist-min").then((m) => (m as unknown as { default: PlotlyModule }).default ?? m));

// Pages written for the dark theme hard-code the bright identity colours in traces; on a light
// background these are re-mapped to their deeper counterparts so lines and markers stay visible.
const LIGHT_REMAP: Record<string, string> = { "#5eead4": "#0f766e", "#f472b6": "#db2777", "#e8ecf5": "#0e1523", "#f8fafc": "#0e1523", "#ffffff": "#0e1523" };

function remapValue(v: unknown, c: ChartColors): unknown {
  if (c.theme !== "light") return v;
  if (typeof v === "string") return LIGHT_REMAP[v.toLowerCase()] ?? v;
  return v;
}

function remapTrace(t: Data, c: ChartColors): Data {
  if (c.theme !== "light") return t;
  const tr = t as unknown as Record<string, unknown>;
  const out: Record<string, unknown> = { ...tr };
  for (const key of ["marker", "line"] as const) {
    const o = tr[key] as Record<string, unknown> | undefined;
    if (o && typeof o === "object" && "color" in o) out[key] = { ...o, color: remapValue(o.color, c) };
  }
  return out as unknown as Data;
}

/** Plotly layout defaults for the current theme (transparent paper, themed text / grid / hover labels). */
export function plotLayoutBase(c: ChartColors): Partial<Layout> {
  const axis = { gridcolor: c.grid, zerolinecolor: c.zeroline, linecolor: c.axisLine, tickcolor: c.axisLine, automargin: true };
  return {
    paper_bgcolor: c.paper,
    plot_bgcolor: c.plot,
    font: { color: c.text, size: 11, family: c.fontFamily },
    colorway: c.palette,
    margin: { l: 48, r: 12, t: 24, b: 36 },
    xaxis: axis,
    yaxis: axis,
    legend: { orientation: "h", y: -0.25, font: { color: c.text } },
    hoverlabel: { bgcolor: c.hoverBg, bordercolor: c.hoverBorder, font: { color: c.hoverText, family: c.fontFamily, size: 11 } },
    modebar: { bgcolor: "rgba(0,0,0,0)", color: c.textMuted, activecolor: c.accent },
  } as Partial<Layout>;
}

/** Thin Plotly wrapper: lazy-loaded, uses Plotly.react for efficient updates. Follows the colour theme. */
export function Plot({ data, layout, height = 220, testId, onClick }: {
  data: Data[];
  layout?: Partial<Layout>;
  height?: number;
  testId?: string;
  onClick?: (pt: { x: unknown; y: unknown; customdata?: unknown; curveNumber: number }) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;
  const colors = useChartColors();
  const base = useMemo(() => plotLayoutBase(colors), [colors]);
  useEffect(() => {
    let alive = true;
    loadPlotly().then((Plotly) => {
      if (!alive || !ref.current) return;
      const merged = {
        ...base,
        height,
        ...layout,
        xaxis: { ...base.xaxis, ...(layout?.xaxis ?? {}) },
        yaxis: { ...base.yaxis, ...(layout?.yaxis ?? {}) },
        legend: { ...base.legend, ...(layout?.legend ?? {}) },
        font: { ...base.font, ...(layout?.font ?? {}) },
      } as Partial<Layout>;
      Plotly.react(ref.current, data.map((t) => remapTrace(t, colors)), merged, { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["select2d", "lasso2d"] });
      const el = ref.current as unknown as { on?: (ev: string, cb: (e: { points: { x: unknown; y: unknown; customdata?: unknown; curveNumber: number }[] }) => void) => void; removeAllListeners?: (ev: string) => void };
      el.removeAllListeners?.("plotly_click");
      el.on?.("plotly_click", (e) => { if (e.points?.[0]) clickRef.current?.(e.points[0]); });
    });
    return () => { alive = false; };
  }, [data, layout, height, base, colors]);
  useEffect(() => () => { if (ref.current) loadPlotly().then((P) => ref.current && P.purge(ref.current)); }, []);
  return <div ref={ref} data-testid={testId} style={{ minHeight: height }} className="w-full" />;
}
