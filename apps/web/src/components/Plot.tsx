import { useEffect, useRef } from "react";
import type { Data, Layout } from "plotly.js-dist-min";
import { PLOT_LAYOUT_BASE } from "../lib/colors";

type PlotlyModule = typeof import("plotly.js-dist-min");
let plotlyPromise: Promise<PlotlyModule> | null = null;
const loadPlotly = () => (plotlyPromise ??= import("plotly.js-dist-min").then((m) => (m as unknown as { default: PlotlyModule }).default ?? m));

/** Thin Plotly wrapper: lazy-loaded, uses Plotly.react for efficient updates. */
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
  useEffect(() => {
    let alive = true;
    loadPlotly().then((Plotly) => {
      if (!alive || !ref.current) return;
      const merged = {
        ...PLOT_LAYOUT_BASE,
        height,
        ...layout,
        xaxis: { ...PLOT_LAYOUT_BASE.xaxis, ...(layout?.xaxis ?? {}) },
        yaxis: { ...PLOT_LAYOUT_BASE.yaxis, ...(layout?.yaxis ?? {}) },
      } as Partial<Layout>;
      Plotly.react(ref.current, data, merged, { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["select2d", "lasso2d"] });
      const el = ref.current as unknown as { on?: (ev: string, cb: (e: { points: { x: unknown; y: unknown; customdata?: unknown; curveNumber: number }[] }) => void) => void; removeAllListeners?: (ev: string) => void };
      el.removeAllListeners?.("plotly_click");
      el.on?.("plotly_click", (e) => { if (e.points?.[0]) clickRef.current?.(e.points[0]); });
    });
    return () => { alive = false; };
  }, [data, layout, height]);
  useEffect(() => () => { if (ref.current) loadPlotly().then((P) => ref.current && P.purge(ref.current)); }, []);
  return <div ref={ref} data-testid={testId} style={{ minHeight: height }} className="w-full" />;
}
