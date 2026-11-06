import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, STATIC_DEMO, api, decodeB64 } from "../lib/api";
import { hexToRgb, useChartColors } from "../lib/colors";
import { type ColorField, useApp } from "../lib/store";
import type { Activity, Attribute, Neuron, NeuronDetail, PartnersResponse, SimSummary } from "../lib/types";
import { BrainScene, type PointStyle, toDisplay } from "../three/BrainScene";
import { Empty, ErrorBox, EvidenceBadge, Loading, Section, Stat, SyntheticBanner, fmt, useAsync, useDatasets, useInterval } from "../components/ui";

const COLOR_FIELDS: { key: ColorField; label: string }[] = [
  { key: "super_class", label: "Super class" },
  { key: "primary_neuropil", label: "Neuropil" },
  { key: "nt_type", label: "Neurotransmitter (predicted)" },
  { key: "cell_type", label: "Cell type (top 254)" },
  { key: "side", label: "Hemisphere" },
  { key: "activity", label: "Simulated activity" },
];

function decodeCodes(a: Attribute): Uint16Array {
  return new Uint16Array(decodeB64(a.codes_b64));
}

export default function Explorer() {
  const navigate = useNavigate();
  const { datasetId, colorField, setColorField, pointSize, setPointSize, opacity, setOpacity, selected, setSelected, highlight, setHighlight, simSessionId, setSimSessionId, setPending } = useApp();
  const datasets = useDatasets();
  const chart = useChartColors();
  const sc = chart.scene;
  const meta = datasets.data?.find((d) => d.dataset_id === datasetId);
  const points = useAsync(() => api.points(datasetId), [datasetId]);
  const attrField = colorField === "activity" ? "super_class" : colorField;
  const attr = useAsync(() => api.attribute(datasetId, attrField), [datasetId, attrField]);
  const sideAttr = useAsync(() => api.attribute(datasetId, "side"), [datasetId]);
  const neuropils = useAsync(() => api.neuropils(datasetId), [datasetId]);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hemi, setHemi] = useState<"all" | "left" | "right">("all");
  const [ortho, setOrtho] = useState(false);
  const [showLabels, setShowLabels] = useState(true);
  const [resetKey, setResetKey] = useState(0);
  const [detail, setDetail] = useState<NeuronDetail | null>(null);
  const [partners, setPartners] = useState<{ up: PartnersResponse | null; down: PartnersResponse | null }>({ up: null, down: null });
  const [minSyn, setMinSyn] = useState(5);
  const [focusPartners, setFocusPartners] = useState(true);
  const [skeleton, setSkeleton] = useState<{ positions: Float32Array; note: string } | null>(null);
  const [skelError, setSkelError] = useState<string | null>(null);
  const [activity, setActivity] = useState<Activity | null>(null);
  const [window_, setWindow] = useState<[number, number]>([0, 100]);
  const [live, setLive] = useState(true);
  const [err, setErr] = useState<Error | null>(null);

  useEffect(() => { setHidden(new Set()); }, [colorField, datasetId]);

  // display-space positions + centre/radius
  const geo = useMemo(() => {
    const p = points.data;
    if (!p) return null;
    const n = p.length / 3;
    let cx = 0, cy = 0, cz = 0, k = 0;
    for (let i = 0; i < n; i++) {
      if (Number.isFinite(p[3 * i])) { cx += p[3 * i]; cy += p[3 * i + 1]; cz += p[3 * i + 2]; k++; }
    }
    const c: [number, number, number] = k ? [cx / k, cy / k, cz / k] : [0, 0, 0];
    const out = new Float32Array(p.length);
    let r = 1;
    for (let i = 0; i < n; i++) {
      if (!Number.isFinite(p[3 * i])) { out[3 * i] = out[3 * i + 1] = out[3 * i + 2] = 0; continue; }
      const d = toDisplay(p[3 * i], p[3 * i + 1], p[3 * i + 2], c);
      out.set(d, 3 * i);
      r = Math.max(r, Math.hypot(d[0], d[1], d[2]));
    }
    return { positions: out, center: c, radius: r * 0.75, n, missing: n - k };
  }, [points.data]);

  // selection -> details, partners, skeleton
  useEffect(() => {
    setDetail(null); setPartners({ up: null, down: null }); setSkeleton(null); setSkelError(null);
    if (!selected) return;
    let alive = true;
    api.neuron(datasetId, selected.root_id).then((d) => alive && setDetail(d), (e) => alive && setErr(e));
    Promise.all([
      api.partners(datasetId, selected.root_id, "upstream", minSyn),
      api.partners(datasetId, selected.root_id, "downstream", minSyn),
    ]).then(([up, down]) => alive && setPartners({ up, down }), (e) => alive && setErr(e));
    return () => { alive = false; };
  }, [selected, datasetId, minSyn]);

  useEffect(() => {
    if (!detail || !geo) return;
    if (!detail.has_skeleton) {
      setSkelError(detail.dataset.synthetic ? "Synthetic neurons have no morphology; their positions are generated." : "No reconstructed skeleton installed for this neuron (run `uv run flymind data fetch skeletons`).");
      return;
    }
    let alive = true;
    api.skeleton(datasetId, detail.root_id, 1).then((s) => {
      if (!alive) return;
      const raw = new Float32Array(decodeB64(s.segments_b64));
      const out = new Float32Array(raw.length);
      for (let i = 0; i < raw.length; i += 3) out.set(toDisplay(raw[i], raw[i + 1], raw[i + 2], geo.center), i);
      setSkeleton({ positions: out, note: `${s.n_segments.toLocaleString()} segments · ${String((s.simplification as { kept_nodes: number }).kept_nodes)} of ${String((s.simplification as { original_nodes: number }).original_nodes)} nodes (LOD ${s.lod})` });
    }, (e: ApiError) => alive && setSkelError(e.message));
    return () => { alive = false; };
  }, [detail, geo, datasetId]);

  // activity overlay
  const sims = useAsync<SimSummary[]>(() => (STATIC_DEMO ? Promise.resolve([]) : api.sims()), [datasetId, colorField]);
  const dsSims = (sims.data ?? []).filter((s) => s.dataset_id === datasetId);
  const activeSim = dsSims.find((s) => s.id === simSessionId) ?? dsSims[0];
  const fetchActivity = useCallback(() => {
    if (colorField !== "activity" || !activeSim) return;
    api.sim(activeSim.id).then((s) => {
      const t1 = live ? s.t_ms : Math.min(window_[1], s.t_ms);
      const t0 = live ? Math.max(0, s.t_ms - (window_[1] - window_[0])) : window_[0];
      return api.activity(s.id, t0, Math.max(t1, t0 + 0.1)).then(setActivity);
    }).catch(setErr);
  }, [colorField, activeSim, live, window_]);
  useEffect(() => { fetchActivity(); }, [fetchActivity]);
  useInterval(fetchActivity, colorField === "activity" && live ? 700 : null);

  // per-point style
  const style: PointStyle | null = useMemo(() => {
    if (!geo || !attr.data) return null;
    const n = geo.n;
    const colors = new Float32Array(n * 3);
    const alpha = new Float32Array(n).fill(opacity);
    const size = new Float32Array(n).fill(1);
    const codes = decodeCodes(attr.data);
    const palette = attr.data.labels.map((l) => hexToRgb(chart.category(attrField, l)));
    const hiddenCodes = new Set(attr.data.labels.flatMap((l, i) => (hidden.has(l) ? [i] : [])));
    for (let i = 0; i < n; i++) {
      const c = palette[codes[i]] ?? sc.fallback;
      colors[3 * i] = c[0]; colors[3 * i + 1] = c[1]; colors[3 * i + 2] = c[2];
      if (hiddenCodes.has(codes[i])) alpha[i] = 0;
    }
    if (points.data) for (let i = 0; i < n; i++) if (!Number.isFinite(points.data[3 * i])) alpha[i] = 0;
    if (hemi !== "all" && sideAttr.data) {
      const sideCodes = decodeCodes(sideAttr.data);
      const want = sideAttr.data.labels.indexOf(hemi);
      for (let i = 0; i < n; i++) if (sideCodes[i] !== want) alpha[i] = 0;
    }
    if (colorField === "activity") {
      for (let i = 0; i < n; i++) { colors[3 * i] = sc.inactive[0]; colors[3 * i + 1] = sc.inactive[1]; colors[3 * i + 2] = sc.inactive[2]; alpha[i] = alpha[i] > 0 ? 0.12 : 0; }
      if (activity) {
        const maxRate = Math.max(1, ...activity.rate_hz.slice(0, 5000));
        activity.idx.forEach((idx, k) => {
          const c = chart.rate(Math.log1p(activity.rate_hz[k]) / Math.log1p(maxRate));
          colors[3 * idx] = c[0]; colors[3 * idx + 1] = c[1]; colors[3 * idx + 2] = c[2];
          alpha[idx] = 1; size[idx] = 2.4;
        });
      }
    }
    const focusIdx = new Set<number>();
    if (selected && focusPartners && (partners.up || partners.down)) {
      for (let i = 0; i < n; i++) alpha[i] = Math.min(alpha[i], 0.06);
      const mark = (list: PartnersResponse | null, rgb: [number, number, number]) => list?.partners.forEach((p) => {
        colors.set(rgb, 3 * p.idx); alpha[p.idx] = 0.95; size[p.idx] = 2.2; focusIdx.add(p.idx);
      });
      mark(partners.up, sc.upstream);
      mark(partners.down, sc.downstream);
    }
    if (highlight) highlight.idx.forEach((i) => { colors.set(sc.highlight, 3 * i); alpha[i] = 1; size[i] = 3; });
    if (selected) { colors.set(sc.selected, 3 * selected.idx); alpha[selected.idx] = 1; size[selected.idx] = 5; }
    return { colors, alpha, size };
  }, [geo, attr.data, attrField, hidden, hemi, sideAttr.data, colorField, activity, selected, partners, focusPartners, highlight, opacity, points.data, chart, sc]);

  const onPick = useCallback((idx: number) => {
    api.neuronAt(datasetId, idx).then(setSelected, setErr);
  }, [datasetId, setSelected]);

  const focus = useMemo<[number, number, number] | null>(() => {
    if (!selected || !geo) return null;
    const p = geo.positions;
    return [p[3 * selected.idx], p[3 * selected.idx + 1], p[3 * selected.idx + 2]];
  }, [selected, geo]);

  const labels = useMemo(() => {
    if (!showLabels || !neuropils.data || !geo) return [];
    return neuropils.data.centroids.map((c) => ({ text: c.neuropil, pos: toDisplay(c.centroid_um[0], c.centroid_um[1], c.centroid_um[2], geo.center) }));
  }, [showLabels, neuropils.data, geo]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT") return;
      if (e.key === "r" || e.key === "R") setResetKey((k) => k + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const sendTo = (kind: "stimulate" | "silence" | "probe", rootIds: string[], label: string) => {
    setPending({ kind, datasetId, rootIds, label });
    navigate("/simulator");
  };

  return (
    <div className="flex h-full min-h-[640px] min-w-[1000px]">
      <aside aria-label="Display and search" className="w-64 shrink-0 space-y-3 overflow-y-auto border-r border-ink-700 p-3 xl:w-80">
        <SyntheticBanner show={!!meta?.synthetic} />
        <SearchPanel datasetId={datasetId} onSelect={setSelected} />
        <Section title="Display">
          <div className="space-y-3 text-sm">
            <div>
            <label className="label" htmlFor="colorby">Colour by</label>
            <select id="colorby" className="input" value={colorField} onChange={(e) => setColorField(e.target.value as ColorField)}>
              {COLOR_FIELDS.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
            </select>
            </div>
            <div className="seg flex" role="group" aria-label="Hemisphere">
              {(["all", "left", "right"] as const).map((h) => (
                <button key={h} aria-pressed={hemi === h} aria-label={h === "all" ? "Both hemispheres" : `${h} hemisphere`} className={`btn flex-1 px-1 py-0.5 text-xs ${hemi === h ? "btn-primary" : ""}`} onClick={() => setHemi(h)}>{h === "all" ? "Both" : `${h[0].toUpperCase()}${h.slice(1)}`}</button>
              ))}
            </div>
            <label className="label !mb-0 flex justify-between" htmlFor="point-size"><span>Point size</span><span className="mono text-ink-400">{pointSize.toFixed(1)}</span>
              </label>
            <input id="point-size" type="range" min={0.5} max={8} step={0.1} value={pointSize} onChange={(e) => setPointSize(+e.target.value)} className="w-full" />
            <label className="label !mb-0 flex justify-between" htmlFor="point-opacity"><span>Opacity</span><span className="mono text-ink-400">{opacity.toFixed(2)}</span>
              </label>
            <input id="point-opacity" type="range" min={0.05} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(+e.target.value)} className="w-full" />
            <div className="flex flex-wrap gap-1">
              <button className="btn py-0.5 text-xs" onClick={() => setOrtho((o) => !o)}>{ortho ? "Perspective" : "Orthographic"}</button>
              <button className="btn py-0.5 text-xs" onClick={() => setResetKey((k) => k + 1)} title="R">Reset camera</button>
              <button className="btn py-0.5 text-xs" onClick={() => setShowLabels((s) => !s)}>{showLabels ? "Hide" : "Show"} labels</button>
            </div>
          </div>
        </Section>
        {colorField === "activity" ? (
          <Section title="Simulated activity">
            {STATIC_DEMO ? <p className="text-xs text-ink-400">Requires the local simulation backend.</p> : dsSims.length === 0 ? (
              <Empty title="No simulation session">Start one in the Brain Simulator, then return here.</Empty>
            ) : (
              <div className="space-y-2 text-xs">
                <select className="input" aria-label="Simulation session" value={activeSim?.id ?? ""} onChange={(e) => setSimSessionId(e.target.value)}>
                  {dsSims.map((s) => <option key={s.id} value={s.id}>{s.id} · {s.mode} · t={fmt.ms(s.t_ms)} · {s.status}</option>)}
                </select>
                <label className="flex items-center gap-2"><input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> Live (last {window_[1] - window_[0]} ms)</label>
                <label className="label">Window start {window_[0]} ms
                  <input type="range" min={0} max={Math.max(100, activeSim?.t_ms ?? 100)} step={10} value={window_[0]} onChange={(e) => { setLive(false); setWindow([+e.target.value, Math.max(+e.target.value + 10, window_[1])]); }} className="w-full" />
                </label>
                <label className="label">Window end {window_[1]} ms
                  <input type="range" min={10} max={Math.max(110, activeSim?.t_ms ?? 110)} step={10} value={window_[1]} onChange={(e) => { setLive(false); setWindow([Math.min(window_[0], +e.target.value - 10), +e.target.value]); }} className="w-full" />
                </label>
                {activity && <div className="text-ink-300">{activity.n_active} active neurons in [{fmt.num(activity.t0_ms, 0)}, {fmt.num(activity.t1_ms, 0)}] ms</div>}
                <EvidenceBadge kind={activeSim?.evidence} />
              </div>
            )}
          </Section>
        ) : (
          <Legend attr={attr.data} field={attrField} hidden={hidden} onToggle={(l) => setHidden((h) => { const n = new Set(h); if (n.has(l)) n.delete(l); else n.add(l); return n; })} />
        )}
      </aside>
      <div className="relative min-w-0 flex-1">
        {(points.loading || attr.loading) && <div className="absolute left-4 top-4 z-10"><Loading label="Loading neurons" /></div>}
        <div className="absolute right-3 top-3 z-10 w-80"><ErrorBox error={points.error ?? attr.error ?? err} /></div>
        {geo && style && (
          <BrainScene positions={geo.positions} style={style} pointSize={pointSize} ortho={ortho} onPick={onPick} labels={labels}
            skeletons={skeleton ? [{ positions: skeleton.positions, color: sc.skeleton }] : []} focus={focus} resetKey={resetKey} radius={geo.radius} />
        )}
        <div className="pointer-events-none absolute bottom-3 right-3 rounded-md border border-ink-700 bg-ink-900/85 px-2.5 py-1 text-[11px] text-ink-400">
          {geo ? `${geo.n.toLocaleString()} neurons as soma/representative points` : ""}
          {geo && geo.missing > 0 ? ` · ${geo.missing} without position` : ""} · µm · click a point to select
        </div>
      </div>
      <aside aria-label="Neuron details" className="w-72 shrink-0 space-y-3 overflow-y-auto border-l border-ink-700 p-3 xl:w-[25rem]">
        {!selected ? (
          <Empty title="No neuron selected">Search on the left or click a point in the 3D view.</Empty>
        ) : !detail ? <Loading label="Loading neuron" /> : (
          <NeuronPanel detail={detail} partners={partners} minSyn={minSyn} setMinSyn={setMinSyn}
            focusPartners={focusPartners} setFocusPartners={setFocusPartners} skeletonNote={skeleton?.note ?? null} skelError={skelError}
            onSelectRoot={(rid) => api.neuron(datasetId, rid).then((n) => setSelected(n), setErr)}
            onSend={sendTo} datasetId={datasetId} onHighlight={setHighlight} onClear={() => { setSelected(null); setHighlight(null); }} />
        )}
        <PathwayPanel datasetId={datasetId} defaultSource={selected?.root_id ?? ""} onPath={(idx, label) => setHighlight({ idx, label })} />
      </aside>
    </div>
  );
}

function Legend({ attr, field, hidden, onToggle }: { attr: Attribute | null; field: string; hidden: Set<string>; onToggle: (l: string) => void }) {
  const colors = useChartColors();
  if (!attr) return null;
  const items = attr.labels.map((l, i) => ({ l, n: attr.counts[i] })).sort((a, b) => b.n - a.n);
  return (
    <Section title={`Legend (${items.length})`}>
      <ul className="-mx-1 max-h-72 space-y-px overflow-y-auto px-1 text-xs" aria-label="Legend">
        {items.map(({ l, n }) => (
          <li key={l}>
            <button className={`flex w-full items-center gap-2 rounded px-1.5 py-1 text-left transition-colors duration-150 hover:bg-ink-800 ${hidden.has(l) ? "opacity-40" : ""}`} onClick={() => onToggle(l)} aria-pressed={!hidden.has(l)} title="Toggle visibility">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colors.category(field, l) }} />
              <span className="flex-1 truncate">{l}</span>
              <span className="mono text-ink-400">{n.toLocaleString()}</span>
            </button>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function SearchPanel({ datasetId, onSelect }: { datasetId: string; onSelect: (n: Neuron) => void }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ total: number; results: Neuron[] } | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const run = (e?: React.FormEvent) => {
    e?.preventDefault();
    api.search(datasetId, { q, limit: 50 }).then(setRes, setErr);
  };
  return (
    <Section title="Find neuron">
      <form onSubmit={run} className="flex gap-1">
        <input className="input" aria-label="Search neurons" placeholder="root ID, cell type (e.g. DNa02)…" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn btn-primary" type="submit">Search</button>
      </form>
      <ErrorBox error={err} />
      {res && (
        <div className="mt-2">
          <div className="mb-1 text-xs text-ink-400">{res.total.toLocaleString()} matches</div>
          <ul className="-mx-1 max-h-60 space-y-px overflow-y-auto px-1 text-xs" data-testid="search-results">
            {res.results.map((n) => (
              <li key={n.root_id}>
                <button className="w-full rounded-md px-2 py-1.5 text-left transition-colors duration-150 hover:bg-ink-800" onClick={() => onSelect(n)}>
                  <span className="font-medium text-ink-100">{n.cell_type ?? "unannotated"}</span>
                  <span className="ml-1 text-ink-400">{n.side ?? ""} · {n.super_class ?? ""}</span>
                  <div className="mono text-[10px] text-ink-400">{n.root_id}</div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}

function NeuronPanel({ detail, partners, minSyn, setMinSyn, focusPartners, setFocusPartners, skeletonNote, skelError, onSelectRoot, onSend, datasetId, onHighlight, onClear }: {
  detail: NeuronDetail;
  partners: { up: PartnersResponse | null; down: PartnersResponse | null };
  minSyn: number;
  setMinSyn: (n: number) => void;
  focusPartners: boolean;
  setFocusPartners: (b: boolean) => void;
  skeletonNote: string | null;
  skelError: string | null;
  onSelectRoot: (rid: string) => void;
  onSend: (kind: "stimulate" | "silence" | "probe", ids: string[], label: string) => void;
  datasetId: string;
  onHighlight: (h: { idx: number[]; label: string } | null) => void;
  onClear: () => void;
}) {
  const [tab, setTab] = useState<"down" | "up">("down");
  const list = tab === "down" ? partners.down : partners.up;
  const label = detail.cell_type ?? detail.root_id;
  return (
    <>
      <Section title="Neuron" right={<button className="btn py-0.5 text-xs" onClick={onClear}>Clear</button>}>
        <div className="space-y-2 text-sm" data-testid="neuron-panel">
          <div>
            <div className="text-lg font-semibold tracking-tight">{detail.cell_type ?? "unannotated"}</div>
            <div className="mono text-xs text-ink-300" data-testid="neuron-root-id">{detail.root_id}</div>
          </div>
          <div className="flex flex-wrap gap-1">
            {detail.dataset.synthetic ? <span className="chip border-amber-500/50 text-amber-300">synthetic</span> : <span className="chip">FlyWire v{detail.dataset.version}</span>}
            {detail.super_class && <span className="chip">{detail.super_class}</span>}
            {detail.side && <span className="chip">{detail.side}</span>}
            {detail.nt_type && <span className="chip" title="Predicted neurotransmitter (Eckstein et al. 2024); an inference, not a measurement">{detail.nt_type}{detail.nt_confidence != null ? ` · p=${detail.nt_confidence.toFixed(2)}` : ""}</span>}
            {detail.primary_neuropil && <span className="chip" title="Neuropil with the most output synapses">{detail.primary_neuropil}</span>}
          </div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            {detail.cell_class && <><dt className="text-ink-400">Class</dt><dd>{detail.cell_class}{detail.cell_sub_class ? ` / ${detail.cell_sub_class}` : ""}</dd></>}
            {detail.hemibrain_type && <><dt className="text-ink-400">Hemibrain type</dt><dd>{detail.hemibrain_type}</dd></>}
            {detail.flow && <><dt className="text-ink-400">Flow</dt><dd>{detail.flow}</dd></>}
            <dt className="text-ink-400">Position (µm)</dt>
            <dd className="mono">{detail.pos_x != null ? [detail.pos_x, detail.pos_y, detail.pos_z].map((v) => ((v ?? 0) / 1000).toFixed(1)).join(", ") : "—"}</dd>
          </dl>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Upstream partners" value={fmt.int(detail.connectivity.upstream_partners)} />
            <Stat label="Downstream partners" value={fmt.int(detail.connectivity.downstream_partners)} />
            <Stat label="Input synapses" value={fmt.int(detail.connectivity.input_synapses)} />
            <Stat label="Output synapses" value={fmt.int(detail.connectivity.output_synapses)} />
          </div>
          <div className="text-xs text-ink-400">{skeletonNote ? <>Skeleton: {skeletonNote}</> : skelError ? <span title="geometry">{skelError}</span> : "Loading geometry…"}</div>
          <div className="flex flex-wrap gap-1">
            <button className="btn btn-primary py-1 text-xs" onClick={() => onSend("stimulate", [detail.root_id], label)} disabled={STATIC_DEMO}>Stimulate in simulator</button>
            <button className="btn py-1 text-xs" onClick={() => onSend("silence", [detail.root_id], label)} disabled={STATIC_DEMO}>Silence</button>
            <button className="btn py-1 text-xs" onClick={() => onSend("probe", [detail.root_id], label)} disabled={STATIC_DEMO}>Record trace</button>
            {detail.source_url && <a className="btn py-1 text-xs" href={detail.source_url} target="_blank" rel="noreferrer">Open in Codex ↗</a>}
          </div>
        </div>
      </Section>
      <Section title="Connectivity" right={
        <label className="flex items-center gap-1 text-[11px] text-ink-400"><input type="checkbox" checked={focusPartners} onChange={(e) => setFocusPartners(e.target.checked)} />Highlight in 3D</label>
      }>
        <div className="mb-2 flex items-center gap-2 text-xs">
          <div className="seg flex" role="tablist" aria-label="Partner direction">
            <button role="tab" aria-selected={tab === "down"} className={`btn py-0.5 text-xs ${tab === "down" ? "btn-primary" : ""}`} onClick={() => setTab("down")}>Outputs ({partners.down?.n_partners ?? "…"})</button>
            <button role="tab" aria-selected={tab === "up"} className={`btn py-0.5 text-xs ${tab === "up" ? "btn-primary" : ""}`} onClick={() => setTab("up")}>Inputs ({partners.up?.n_partners ?? "…"})</button>
          </div>
          <label className="ml-auto flex items-center gap-1">≥<input aria-label="Minimum synapses" type="number" className="input w-14 py-0.5" min={1} value={minSyn} onChange={(e) => setMinSyn(Math.max(1, +e.target.value))} /> syn</label>
        </div>
        <p className="mb-2 text-[11px] leading-snug text-ink-400">Counts are reconstructed synapses. Sign follows the presynaptic neuron's predicted transmitter (model assumption). <span className="text-sky-300">Inputs</span> / <span className="text-pink-300">outputs</span> are coloured in 3D; nearby points are not necessarily connected.</p>
        <div className="max-h-80 overflow-y-auto">
          <table className="table" data-testid="partners-table">
            <thead><tr><th>Partner</th><th>Syn</th><th>%</th><th>±</th></tr></thead>
            <tbody>
              {(list?.partners ?? []).slice(0, 150).map((p) => (
                <tr key={p.root_id} className="cursor-pointer hover:bg-ink-800" onClick={() => onSelectRoot(p.root_id)}>
                  <td><div>{p.cell_type ?? "—"}</div><div className="mono text-[10px] text-ink-400">{p.root_id}</div></td>
                  <td className="mono">{p.syn_count}</td>
                  <td className="mono">{(p.fraction_of_total * 100).toFixed(1)}</td>
                  <td className={p.sign > 0 ? "text-emerald-300" : "text-rose-300"}>{p.sign > 0 ? "+" : "−"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list && list.partners.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            <button className="btn py-0.5 text-xs" disabled={STATIC_DEMO} onClick={() => onSend("stimulate", list.partners.slice(0, 50).map((p) => p.root_id), `${tab === "down" ? "outputs" : "inputs"} of ${label}`)}>Stimulate these partners</button>
            <button className="btn py-0.5 text-xs" onClick={() => onHighlight({ idx: list.partners.map((p) => p.idx), label: "partners" })}>Pin highlight</button>
            {!STATIC_DEMO && <a className="btn py-0.5 text-xs" href={api.subgraphCsvUrl(datasetId, detail.root_id, 1, "both", minSyn)}>Export subgraph CSV</a>}
          </div>
        )}
      </Section>
    </>
  );
}

function PathwayPanel({ datasetId, defaultSource, onPath }: { datasetId: string; defaultSource: string; onPath: (idx: number[], label: string) => void }) {
  const [src, setSrc] = useState("");
  const [tgt, setTgt] = useState("");
  const [minSyn, setMinSyn] = useState(5);
  const [res, setRes] = useState<Awaited<ReturnType<typeof api.pathways>> | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  useEffect(() => { if (defaultSource) setSrc(defaultSource); }, [defaultSource]);
  if (STATIC_DEMO) return null;
  return (
    <Section title="Trace pathway (shortest directed path)">
      <div className="space-y-1.5 text-xs">
        <input className="input mono" aria-label="Pathway source" placeholder="source root ID(s)" value={src} onChange={(e) => setSrc(e.target.value)} />
        <input className="input mono" aria-label="Pathway target" placeholder="target root ID(s)" value={tgt} onChange={(e) => setTgt(e.target.value)} />
        <div className="flex items-center gap-2">
          <label>≥ syn/hop <input type="number" className="input w-16 py-0.5" value={minSyn} min={1} onChange={(e) => setMinSyn(+e.target.value)} /></label>
          <button className="btn btn-primary ml-auto py-1 text-xs" onClick={() => api.pathways(datasetId, src, tgt, minSyn, 6).then((r) => { setRes(r); setErr(null); if (r.found) onPath(r.path.map((n) => n.idx), "pathway"); }, setErr)}>Trace</button>
        </div>
        <ErrorBox error={err} />
        {res && (res.found ? (
          <ol className="space-y-0.5" data-testid="pathway-result">
            {res.path.map((n, i) => (
              <li key={n.root_id}>
                <span className="text-ink-100">{i + 1}. {n.cell_type ?? "—"}</span> <span className="mono text-[10px] text-ink-400">{n.root_id}</span>
                {res.edges[i] && <div className="pl-4 text-[10px] text-ink-400">↓ {res.edges[i].syn_count} synapses ({res.edges[i].sign > 0 ? "excitatory" : "inhibitory"} sign)</div>}
              </li>
            ))}
          </ol>
        ) : <p className="text-ink-400">{res.message}</p>)}
      </div>
    </Section>
  );
}
