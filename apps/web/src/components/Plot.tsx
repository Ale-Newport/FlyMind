import { useEffect, useMemo, useRef } from "react";
import type { Annotation, Data, Layout } from "plotly.js-dist-min";
import { type ChartColors, useChartColors } from "../lib/colors";

type PlotlyModule = typeof import("plotly.js-dist-min");
let plotlyPromise: Promise<PlotlyModule> | null = null;
const loadPlotly = () => (plotlyPromise ??= import("plotly.js-dist-min").then((m) => (m as unknown as { default: PlotlyModule }).default ?? m));

/**
 * Plotly layout defaults for the current theme: transparent paper, Geist at 11px in a muted ink, hairline
 * gridlines, a single baseline axis, no zero lines, no tick marks on the value axis, and a legend that sits
 * quietly above the plot's left edge.
 */
export function plotLayoutBase(c: ChartColors): Partial<Layout> {
  const axis = { gridcolor: c.grid, gridwidth: 1, zeroline: false, automargin: true, tickfont: { color: c.textMuted, size: 11 }, title: { font: { color: c.textMuted, size: 11 }, standoff: 8 } };
  return {
    paper_bgcolor: c.paper,
    plot_bgcolor: c.plot,
    font: { color: c.textMuted, size: 11, family: c.fontFamily },
    colorway: c.palette,
    margin: { l: 44, r: 8, t: 8, b: 36 },
    xaxis: { ...axis, showline: true, linecolor: c.axisLine, ticks: "outside", ticklen: 4, tickcolor: c.axisLine },
    yaxis: { ...axis, showline: false, ticks: "" },
    legend: { orientation: "h", x: 0, y: 1.08, xanchor: "left", yanchor: "bottom", font: { color: c.text, size: 11 }, bgcolor: "rgba(0,0,0,0)" },
    hoverlabel: { bgcolor: c.hoverBg, bordercolor: c.hoverBorder, font: { color: c.hoverText, family: c.monoFamily, size: 11 } },
    modebar: { bgcolor: "rgba(0,0,0,0)", color: c.textMuted, activecolor: c.accent },
  } as Partial<Layout>;
}

function endLabelAnnotations(data: Data[], c: ChartColors): Partial<Annotation>[] {
  const out: Partial<Annotation>[] = [];
  data.forEach((t, i) => {
    const tr = t as unknown as { type?: string; x?: unknown[]; y?: unknown[]; name?: string; line?: { color?: string } };
    if ((tr.type ?? "scatter") !== "scatter" || !tr.x?.length || !tr.y?.length || !tr.name) return;
    const k = Math.min(tr.x.length, tr.y.length) - 1;
    out.push({
      x: tr.x[k] as number, y: tr.y[k] as number, text: tr.name, showarrow: false, xanchor: "left", yanchor: "middle", xshift: 6,
      font: { color: tr.line?.color ?? c.palette[i % c.palette.length], size: 11, family: c.fontFamily },
    });
  });
  return out;
}

/** Thin Plotly wrapper: lazy-loaded, uses Plotly.react for efficient updates. Follows the colour theme. */
export function Plot({ data, layout, height = 220, testId, onClick, endLabels = false }: {
  data: Data[];
  layout?: Partial<Layout>;
  height?: number;
  testId?: string;
  onClick?: (pt: { x: unknown; y: unknown; customdata?: unknown; curveNumber: number }) => void;
  /** label line series directly at their last point instead of using a legend */
  endLabels?: boolean;
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
        margin: { ...base.margin, ...(endLabels ? { r: 72 } : {}), ...(layout?.margin ?? {}) },
        ...(endLabels ? { showlegend: false, annotations: [...(layout?.annotations ?? []), ...endLabelAnnotations(data, colors)] } : {}),
      } as Partial<Layout>;
      Plotly.react(ref.current, data, merged, { displaylogo: false, responsive: true, displayModeBar: "hover", modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toImage"] });
      const el = ref.current as unknown as { on?: (ev: string, cb: (e: { points: { x: unknown; y: unknown; customdata?: unknown; curveNumber: number }[] }) => void) => void; removeAllListeners?: (ev: string) => void };
      el.removeAllListeners?.("plotly_click");
      el.on?.("plotly_click", (e) => { if (e.points?.[0]) clickRef.current?.(e.points[0]); });
    });
    return () => { alive = false; };
  }, [data, layout, height, base, colors, endLabels]);
  useEffect(() => () => { if (ref.current) loadPlotly().then((P) => ref.current && P.purge(ref.current)); }, []);
  return <div ref={ref} data-testid={testId} style={{ minHeight: height }} className="w-full" />;
}
