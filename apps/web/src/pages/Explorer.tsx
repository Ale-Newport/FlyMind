import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, STATIC_DEMO, api, decodeB64 } from "../lib/api";
import { hexToRgb, rgbCss, useChartColors } from "../lib/colors";
import { type ColorField, useApp } from "../lib/store";
import type { Activity, Attribute, Neuron, NeuronDetail, PartnersResponse, SimSummary } from "../lib/types";
import { BrainScene, type PointStyle, toDisplay } from "../three/BrainScene";
import { Block, Empty, ErrorBox, EvidenceBadge, Group, KV, Loading, Seg, Slider, SyntheticBanner, fmt, useAsync, useDatasets, useInterval } from "../components/ui";
import { Icon } from "../components/Icon";

const COLOR_FIELDS: { key: ColorField; label: string }[] = [
  { key: "super_class", label: "Super class" },
  { key: "primary_neuropil", label: "Neuropil" },
  { key: "nt_type", label: "Neurotransmitter (predicted)" },
  { key: "cell_type", label: "Cell type (254 most common)" },
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
      setSkelError(detail.dataset.synthetic ? "Synthetic neurons have no morphology; their positions are generated." : "No reconstructed skeleton is installed for this neuron. Run `uv run flymind data fetch skeletons`.");
      return;
    }
    let alive = true;
    api.skeleton(datasetId, detail.root_id, 1).then((s) => {
      if (!alive) return;
      const raw = new Float32Array(decodeB64(s.segments_b64));
      const out = new Float32Array(raw.length);
      for (let i = 0; i < raw.length; i += 3) out.set(toDisplay(raw[i], raw[i + 1], raw[i + 2], geo.center), i);
      setSkeleton({ positions: out, note: `${s.n_segments.toLocaleString()} segments, ${(s.simplification as { kept_nodes: number }).kept_nodes.toLocaleString()} of ${(s.simplification as { original_nodes: number }).original_nodes.toLocaleString()} nodes (LOD ${s.lod})` });
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
    <div className="tool min-h-[600px] min-w-[1000px]">
      <h1 className="sr-only">Brain explorer</h1>
      <aside aria-label="Display and search" className="rail">
        {meta?.synthetic && <div className="p-4"><SyntheticBanner show /></div>}
        <Group title="Find a neuron"><SearchPanel datasetId={datasetId} onSelect={setSelected} /></Group>
        <Group title="Display">
          <div className="space-y-4">
            <div>
              <label className="label" htmlFor="colorby">Colour by</label>
              <select id="colorby" className="input" value={colorField} onChange={(e) => setColorField(e.target.value as ColorField)}>
                {COLOR_FIELDS.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
              </select>
            </div>
            <div>
              <span className="label">Hemisphere</span>
              <Seg kind="pressed" fill label="Hemisphere" value={hemi} onChange={setHemi} options={[
                { value: "all", label: "Both", ariaLabel: "Both hemispheres" },
                { value: "left", label: "Left", ariaLabel: "Left hemisphere" },
                { value: "right", label: "Right", ariaLabel: "Right hemisphere" },
              ]} />
            </div>
            <div>
              <span className="label">Projection</span>
              <Seg kind="radio" fill label="Projection" value={ortho ? "ortho" : "persp"} onChange={(v) => setOrtho(v === "ortho")} options={[
                { value: "persp", label: "Perspective" }, { value: "ortho", label: "Orthographic" },
              ]} />
            </div>
            <Slider label="Point size" value={pointSize} min={0.5} max={8} step={0.1} onChange={setPointSize} format={(v) => v.toFixed(1)} />
            <Slider label="Opacity" value={opacity} min={0.05} max={1} step={0.05} onChange={setOpacity} format={(v) => v.toFixed(2)} />
            <div className="flex items-center justify-between">
              <label className="check"><input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /> Neuropil labels</label>
              <button className="btn btn-sm" onClick={() => setResetKey((k) => k + 1)} title="Shortcut: R"><Icon name="crosshair" size={14} />Reset camera</button>
            </div>
          </div>
        </Group>
        {colorField === "activity" ? (
          <Group title="Simulated activity">
            {STATIC_DEMO ? <p className="text-xs text-ink-3">Requires the local simulation backend.</p> : dsSims.length === 0 ? (
              <Empty title="No simulation session." className="!py-0">Start one in the brain simulator, then return here.</Empty>
            ) : (
              <div className="space-y-4">
                <select className="input" aria-label="Simulation session" value={activeSim?.id ?? ""} onChange={(e) => setSimSessionId(e.target.value)}>
                  {dsSims.map((s) => <option key={s.id} value={s.id}>{s.id} · {s.mode} · t = {fmt.ms(s.t_ms)} · {s.status}</option>)}
                </select>
                <label className="check"><input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> Follow the latest {window_[1] - window_[0]} ms</label>
                <Slider label="Window start" unit="ms" value={window_[0]} min={0} max={Math.max(100, activeSim?.t_ms ?? 100)} step={10} onChange={(v) => { setLive(false); setWindow([v, Math.max(v + 10, window_[1])]); }} />
                <Slider label="Window end" unit="ms" value={window_[1]} min={10} max={Math.max(110, activeSim?.t_ms ?? 110)} step={10} onChange={(v) => { setLive(false); setWindow([Math.min(window_[0], v - 10), v]); }} />
                {activity && <p className="text-xs text-ink-2"><span className="mono">{activity.n_active.toLocaleString()}</span> active neurons in [{fmt.num(activity.t0_ms, 0)}, {fmt.num(activity.t1_ms, 0)}] ms</p>}
                <EvidenceBadge kind={activeSim?.evidence} />
              </div>
            )}
          </Group>
        ) : (
          <Legend attr={attr.data} field={attrField} hidden={hidden} onToggle={(l) => setHidden((h) => { const n = new Set(h); if (n.has(l)) n.delete(l); else n.add(l); return n; })} />
        )}
      </aside>
      <div className="stage">
        {(points.loading || attr.loading) && <div className="absolute left-4 top-4 z-10"><Loading label="Loading neurons" /></div>}
        <div className="absolute right-4 top-4 z-10 w-80"><ErrorBox error={points.error ?? attr.error ?? err} /></div>
        {geo && style && (
          <BrainScene positions={geo.positions} style={style} pointSize={pointSize} ortho={ortho} onPick={onPick} labels={labels}
            skeletons={skeleton ? [{ positions: skeleton.positions, color: sc.skeleton }] : []} focus={focus} resetKey={resetKey} radius={geo.radius} />
        )}
        <div className="overlay pointer-events-none absolute bottom-3 right-3 text-right">
          {geo ? <><span className="mono">{geo.n.toLocaleString()}</span> neurons, drawn at the soma or a representative point</> : ""}
          {geo && geo.missing > 0 ? <>; <span className="mono">{geo.missing}</span> without a position</> : ""}. Units µm. Click a point to select it.
        </div>
      </div>
      <aside aria-label="Neuron details" className="inspector">
        {!selected ? (
          <Block><Empty title="No neuron selected.">Search in the left rail, or click a point in the view.</Empty></Block>
        ) : !detail ? <Block><Loading label="Loading neuron" /></Block> : (
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
    <Group title="Legend" meta={`${items.length} classes`}>
      <ul className="-mx-2 max-h-72 overflow-y-auto px-2 text-xs" aria-label="Legend">
        {items.map(({ l, n }) => (
          <li key={l}>
            <button className={`flex w-full items-center gap-2 px-1 py-[3px] text-left transition-colors duration-150 hover:bg-paper-3 ${hidden.has(l) ? "opacity-40" : ""}`} onClick={() => onToggle(l)} aria-pressed={!hidden.has(l)} title="Show or hide this class">
              <span className="h-2 w-2 shrink-0" style={{ background: colors.category(field, l) }} />
              <span className={`flex-1 truncate ${hidden.has(l) ? "line-through" : ""}`}>{l}</span>
              <span className="mono text-ink-3">{n.toLocaleString()}</span>
            </button>
          </li>
        ))}
      </ul>
    </Group>
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
    <>
      <form onSubmit={run} className="flex gap-2">
        <input className="input" aria-label="Search neurons" placeholder="Root ID or cell type" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn btn-primary" type="submit">Search</button>
      </form>
      <div className="mt-2"><ErrorBox error={err} /></div>
      {res && (
        <div className="mt-3">
          <div className="mb-1 text-xs text-ink-3"><span className="mono">{res.total.toLocaleString()}</span> matches{res.total > res.results.length ? `, showing ${res.results.length}` : ""}</div>
          <ul className="-mx-2 max-h-60 overflow-y-auto px-2 text-xs" data-testid="search-results">
            {res.results.map((n) => (
              <li key={n.root_id}>
                <button className="w-full border-t border-rule px-1 py-1.5 text-left transition-colors duration-150 hover:bg-paper-3" onClick={() => onSelect(n)}>
                  <span className="text-ink">{n.cell_type ?? "unannotated"}</span>
                  <span className="ml-2 text-ink-3">{[n.side, n.super_class].filter(Boolean).join(", ")}</span>
                  <div className="mono text-[11px] text-ink-3">{n.root_id}</div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
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
  const { scene } = useChartColors();
  const list = tab === "down" ? partners.down : partners.up;
  const label = detail.cell_type ?? detail.root_id;
  const pos = detail.pos_x != null ? [detail.pos_x, detail.pos_y, detail.pos_z].map((v) => ((v ?? 0) / 1000).toFixed(1)).join(", ") : "–";
  return (
    <>
      <Block>
        <div data-testid="neuron-panel">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="t-head break-words">{detail.cell_type ?? "Unannotated"}</h2>
              <div className="mono mt-0.5 text-xs text-ink-3" data-testid="neuron-root-id">{detail.root_id}</div>
            </div>
            <button className="btn btn-sm btn-quiet shrink-0" onClick={onClear}><Icon name="close" size={12} />Clear</button>
          </div>
          <KV className="mt-4" rows={[
            ["Dataset", detail.dataset.synthetic ? "Synthetic" : `FlyWire v${detail.dataset.version}`],
            detail.super_class && ["Super class", detail.super_class],
            detail.cell_class && ["Class", `${detail.cell_class}${detail.cell_sub_class ? ` / ${detail.cell_sub_class}` : ""}`],
            detail.side && ["Side", detail.side],
            detail.nt_type && [<span key="nt" title="Predicted neurotransmitter (Eckstein et al. 2024); an inference, not a measurement">Transmitter, predicted</span>, `${detail.nt_type}${detail.nt_confidence != null ? `  p = ${detail.nt_confidence.toFixed(2)}` : ""}`],
            detail.primary_neuropil && [<span key="np" title="Neuropil with the most output synapses">Primary neuropil</span>, detail.primary_neuropil],
            detail.hemibrain_type && ["Hemibrain type", detail.hemibrain_type],
            detail.flow && ["Flow", detail.flow],
            ["Position", pos, "µm"],
          ]} />
          <p className="mt-3 text-xs text-ink-3">{skeletonNote ? <>Skeleton: {skeletonNote}</> : skelError ? skelError : "Loading geometry…"}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="btn btn-primary btn-sm" onClick={() => onSend("stimulate", [detail.root_id], label)} disabled={STATIC_DEMO}>Stimulate in simulator</button>
            <button className="btn btn-sm" onClick={() => onSend("silence", [detail.root_id], label)} disabled={STATIC_DEMO}>Silence</button>
            <button className="btn btn-sm" onClick={() => onSend("probe", [detail.root_id], label)} disabled={STATIC_DEMO}>Record trace</button>
            {detail.source_url && <a className="btn btn-sm no-underline hover:text-ink" href={detail.source_url} target="_blank" rel="noreferrer">Open in Codex <Icon name="external" size={12} /></a>}
          </div>
        </div>
      </Block>
      <Block title="Connectivity" right={<label className="check text-xs"><input type="checkbox" checked={focusPartners} onChange={(e) => setFocusPartners(e.target.checked)} />Highlight in 3D</label>}>
        <KV rows={[
          ["Upstream partners", fmt.int(detail.connectivity.upstream_partners)],
          ["Downstream partners", fmt.int(detail.connectivity.downstream_partners)],
          ["Input synapses", fmt.int(detail.connectivity.input_synapses)],
          ["Output synapses", fmt.int(detail.connectivity.output_synapses)],
        ]} />
        <div className="mt-5">
          <Seg kind="tab" fill label="Partner direction" value={tab} onChange={setTab} options={[
            { value: "down", label: `Outputs (${partners.down?.n_partners ?? "…"})` },
            { value: "up", label: `Inputs (${partners.up?.n_partners ?? "…"})` },
          ]} />
          <label className="mt-3 flex items-center justify-between gap-2 text-xs text-ink-3">Minimum synapses per partner
            <input aria-label="Minimum synapses" type="number" className="input input-sm !w-14" min={1} value={minSyn} onChange={(e) => setMinSyn(Math.max(1, +e.target.value))} />
          </label>
        </div>
        <div className="mt-3 max-h-80 overflow-y-auto">
          <table className="tbl" data-testid="partners-table">
            <thead><tr><th>Partner</th><th className="num">Syn</th><th className="num">%</th><th className="num">Sign</th></tr></thead>
            <tbody>
              {(list?.partners ?? []).slice(0, 150).map((p) => (
                <tr key={p.root_id} className="row-link" onClick={() => onSelectRoot(p.root_id)}>
                  <td><div>{p.cell_type ?? "–"}</div><div className="mono text-[11px] text-ink-3">{p.root_id}</div></td>
                  <td className="num">{p.syn_count}</td>
                  <td className="num">{(p.fraction_of_total * 100).toFixed(1)}</td>
                  <td className="num" style={{ color: p.sign > 0 ? "var(--ok)" : "var(--danger)" }} aria-label={p.sign > 0 ? "excitatory" : "inhibitory"}>{p.sign > 0 ? "+" : "−"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs leading-5 text-ink-3">
          Counts are reconstructed synapses. The sign follows the presynaptic neuron's predicted transmitter, a model assumption. In 3D, inputs are
          drawn <span className="inline-block h-2 w-2 align-baseline" style={{ background: rgbCss(scene.upstream) }} /> blue and outputs <span className="inline-block h-2 w-2 align-baseline" style={{ background: rgbCss(scene.downstream) }} /> rose; nearby points are not necessarily connected.
        </p>
        {list && list.partners.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn btn-sm" disabled={STATIC_DEMO} onClick={() => onSend("stimulate", list.partners.slice(0, 50).map((p) => p.root_id), `${tab === "down" ? "outputs" : "inputs"} of ${label}`)}>Stimulate these partners</button>
            <button className="btn btn-sm" onClick={() => onHighlight({ idx: list.partners.map((p) => p.idx), label: "partners" })}>Pin highlight</button>
            {!STATIC_DEMO && <a className="btn btn-sm no-underline hover:text-ink" href={api.subgraphCsvUrl(datasetId, detail.root_id, 1, "both", minSyn)}><Icon name="download" size={12} />Subgraph CSV</a>}
          </div>
        )}
      </Block>
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
    <Group title="Trace a pathway" defaultOpen={false}>
      <div className="space-y-2 text-xs">
        <p className="text-ink-3">Shortest directed path between two neurons.</p>
        <input className="input mono !text-left" aria-label="Pathway source" placeholder="Source root ID(s)" value={src} onChange={(e) => setSrc(e.target.value)} />
        <input className="input mono !text-left" aria-label="Pathway target" placeholder="Target root ID(s)" value={tgt} onChange={(e) => setTgt(e.target.value)} />
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-ink-3">at least <input type="number" className="input input-sm !w-12" value={minSyn} min={1} onChange={(e) => setMinSyn(+e.target.value)} /> syn per hop</label>
          <button className="btn btn-primary btn-sm ml-auto" onClick={() => api.pathways(datasetId, src, tgt, minSyn, 6).then((r) => { setRes(r); setErr(null); if (r.found) onPath(r.path.map((n) => n.idx), "pathway"); }, setErr)}>Trace</button>
        </div>
        <ErrorBox error={err} />
        {res && (res.found ? (
          <ol className="pt-1" data-testid="pathway-result">
            {res.path.map((n, i) => (
              <li key={n.root_id}>
                <span className="text-ink">{i + 1}. {n.cell_type ?? "–"}</span> <span className="mono text-[11px] text-ink-3">{n.root_id}</span>
                {res.edges[i] && <div className="my-1 ml-1.5 border-l border-rule-strong pl-3 text-[11px] text-ink-3">{res.edges[i].syn_count} synapses, {res.edges[i].sign > 0 ? "excitatory" : "inhibitory"} sign</div>}
              </li>
            ))}
          </ol>
        ) : <p className="text-ink-3">{res.message}</p>)}
      </div>
    </Group>
  );
}
