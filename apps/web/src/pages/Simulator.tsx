import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { STATIC_DEMO, api, wsUrl } from "../lib/api";
import { useApp } from "../lib/store";
import type { Activity, InterventionSpec, Selector, SimFrame, SimSummary, StimulusSpec } from "../lib/types";
import { Plot } from "../components/Plot";
import { Block, Empty, ErrorBox, EvidenceBadge, Field, Figure, Group, KV, Notice, Seg, SelectorInput, Slider, SyntheticBanner, fmt, useAsync, useDatasets, useInterval } from "../components/ui";
import { Icon } from "../components/Icon";
import { useChartColors } from "../lib/colors";

type Mode = "full" | "circuit" | "region" | "demo";
const RASTER_WINDOW_MS = 500;

export default function Simulator() {
  const { datasetId, simSessionId, setSimSessionId, pending, setPending, setSelected } = useApp();
  const datasets = useDatasets();
  const meta = datasets.data?.find((d) => d.dataset_id === datasetId);
  const [session, setSession] = useState<SimSummary | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  // restore session for this dataset
  useEffect(() => {
    if (STATIC_DEMO) return;
    api.sims().then((list) => {
      const s = list.find((x) => x.id === simSessionId && x.dataset_id === datasetId) ?? list.find((x) => x.dataset_id === datasetId) ?? null;
      setSession(s);
      if (s) setSimSessionId(s.id);
    }, setErr);
  }, [datasetId]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Responses can resolve out of order (e.g. a status refresh issued before "start");
  // only the most recently issued request may update the session state.
  const seq = useRef(0);
  const act = useCallback(async (fn: () => Promise<SimSummary>) => {
    const my = ++seq.current;
    setBusy(true);
    try {
      const s = await fn();
      if (my === seq.current) { setSession(s); setErr(null); }
      return s;
    } catch (e) { if (my === seq.current) setErr(e as Error); return null; } finally { setBusy(false); }
  }, []);

  // apply actions requested from the explorer
  useEffect(() => {
    if (!pending || !session || pending.datasetId !== session.dataset_id) return;
    const sel: Selector = { root_ids: pending.rootIds };
    const p = pending;
    setPending(null);
    if (p.kind === "stimulate") act(() => api.addStimulus(session.id, { kind: "poisson", selector: sel, rate_hz: 150, start_ms: 0, stop_ms: 500, relative: true, label: `stim ${p.label}` }));
    if (p.kind === "silence") act(() => api.addIntervention(session.id, { kind: "silence", selector: sel, mode: "block_output", label: `silence ${p.label}` }));
    if (p.kind === "probe") act(() => api.setProbes(session.id, Array.from(new Set([...session.probe_root_ids, ...p.rootIds])).slice(0, 64)));
  }, [pending, session, setPending, act]);

  if (STATIC_DEMO) {
    return <div className="mx-auto max-w-3xl px-8 py-12"><Empty title="The brain simulator needs the local backend.">The leaky integrate-and-fire engine runs in Python (Numba and Brian2). Run <code>make dev</code> on your machine to use it.</Empty></div>;
  }

  return (
    <div className="tool min-w-[960px]">
      <h1 className="sr-only">Brain simulator</h1>
      <aside aria-label="Simulation setup" className="rail">
        {(meta?.synthetic || (pending && (!session || pending.datasetId !== session.dataset_id))) && (
          <div className="space-y-3 p-4">
            <SyntheticBanner show={!!meta?.synthetic} />
            {pending && (!session || pending.datasetId !== session.dataset_id) && (
              <Notice tone="accent" role="status">
                Pending from Explorer: {pending.kind} {pending.label} ({pending.rootIds.length} neuron{pending.rootIds.length > 1 ? "s" : ""}). Create a session to apply it.
              </Notice>
            )}
          </div>
        )}
        <Group title="Network and model">
          <SetupPanel datasetId={datasetId} hasSession={!!session} onCreate={(cfg) => act(async () => {
            if (session) await api.deleteSim(session.id).catch(() => undefined);
            const s = await api.createSim(cfg);
            setSimSessionId(s.id);
            return s;
          })} busy={busy} />
        </Group>
        {session && <Group title="Stimulation"><StimulusPanel session={session} act={act} /></Group>}
        {session && <Group title="Silencing and perturbation" defaultOpen={false}><InterventionPanel session={session} act={act} /></Group>}
      </aside>
      {!session ? (
        <div className="min-w-0 flex-1 overflow-y-auto px-8 py-8">
          <ErrorBox error={err} />
          <Empty title="No simulation session." className="max-w-[56ch]">
            Choose a network in the left rail and press Create session. Demo mode runs the small synthetic network; full-brain mode uses the imported FlyWire dataset.
          </Empty>
        </div>
      ) : (
        <Running session={session} act={act} err={err} onPickNeuron={(rid) => api.neuron(session.dataset_id, rid).then(setSelected)} />
      )}
    </div>
  );
}

function SetupPanel({ datasetId, hasSession, onCreate, busy }: { datasetId: string; hasSession: boolean; onCreate: (cfg: Record<string, unknown>) => void; busy: boolean }) {
  const datasets = useDatasets();
  const meta = datasets.data?.find((d) => d.dataset_id === datasetId);
  const params = useAsync(() => api.params(), []);
  const neuropils = useAsync(() => api.neuropils(datasetId), [datasetId]);
  const [mode, setMode] = useState<Mode>("full");
  const [sel, setSel] = useState<Selector>({});
  const [depth, setDepth] = useState(1);
  const [regions, setRegions] = useState<string[]>([]);
  const [seed, setSeed] = useState(0);
  const [duration, setDuration] = useState(10_000);
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  useEffect(() => { setMode(meta?.synthetic ? "demo" : "full"); }, [meta?.synthetic]);
  const editable = ["w_syn_mV", "v_threshold_mV", "tau_m_ms", "tau_syn_ms", "t_refractory_ms", "delay_ms", "poisson_weight_factor"];
  const create = () => onCreate({
    dataset_id: datasetId,
    network: { mode, selection: mode === "circuit" ? sel : null, expand_depth: depth, neuropils: regions },
    params: { ...(params.data?.defaults ?? {}), ...overrides },
    seed, max_duration_ms: duration, label: `${mode} session`,
  });
  const MODES: Record<Mode, { label: string; title: string }> = {
    full: { label: "Full", title: "Entire imported graph" },
    circuit: { label: "Circuit", title: "Selected neurons, optionally with their k-hop neighbourhood" },
    region: { label: "Region", title: "Neurons whose primary neuropil is selected" },
    demo: { label: "Demo", title: "Synthetic fixture only" },
  };
  return (
    <div className="space-y-4">
      <Seg kind="radio" fill label="Simulation mode" value={mode} onChange={setMode}
        options={(["full", "circuit", "region", "demo"] as Mode[]).map((m) => ({ value: m, label: MODES[m].label, title: MODES[m].title, disabled: (m === "demo") !== !!meta?.synthetic && (m === "demo" || m === "region") }))} />
      {mode === "full" && <p className="text-xs text-ink-3">{meta ? `${meta.n_neurons.toLocaleString()} neurons and ${meta.n_edges.toLocaleString()} connections from ${meta.synthetic ? "the synthetic fixture" : `${meta.name} v${meta.version}`}.` : ""}</p>}
      {mode === "demo" && <p className="text-xs text-ink-3">The small synthetic network. Useful for learning the controls; it has no biological meaning.</p>}
      {mode === "circuit" && (
        <>
          <SelectorInput datasetId={datasetId} value={sel} onChange={setSel} />
          <Slider label="Neighbourhood" unit={depth === 1 ? "hop" : "hops"} value={depth} min={0} max={3} onChange={setDepth} hint="Adds up- and downstream partners with at least 5 synapses" />
        </>
      )}
      {mode === "region" && (
        <Field label="Neuropils" hint="Neurons are assigned to their primary neuropil, the one with most of their output synapses">
          <select multiple aria-label="Neuropils" className="input h-28" value={regions} onChange={(e) => setRegions(Array.from(e.target.selectedOptions).map((o) => o.value))}>
            {(neuropils.data?.centroids ?? []).sort((a, b) => a.neuropil.localeCompare(b.neuropil)).map((c) => <option key={c.neuropil} value={c.neuropil}>{c.neuropil} ({c.neurons})</option>)}
          </select>
        </Field>
      )}
      <div className="grid grid-cols-2 gap-3">
        <Field label="Random seed"><input type="number" className="input" value={seed} min={0} onChange={(e) => setSeed(+e.target.value)} /></Field>
        <Field label="Max duration" unit="ms"><input type="number" className="input" value={duration} min={10} max={600000} onChange={(e) => setDuration(+e.target.value)} /></Field>
      </div>
      <details className="disclose text-xs">
        <summary>Model parameters</summary>
        <div className="mt-3 space-y-1.5">
          <p className="mb-2 text-ink-3">Defaults follow Shiu et al. (2024). dt = 0.1 ms with exact integration.</p>
          {params.data && editable.map((k) => {
            const info = params.data!.info[k];
            const ref = info.status === "reference_model";
            return (
              <label key={k} className="grid grid-cols-[1fr_4.5rem_2rem] items-center gap-2" title={`${info.description}. Source: ${info.source} [${info.status}]`}>
                <span className="mono truncate text-[11px]">{k}</span>
                <input type="number" step="any" className="input input-sm" value={overrides[k] ?? (params.data!.defaults[k] as number)} onChange={(e) => setOverrides({ ...overrides, [k]: +e.target.value })} />
                <span className="text-[11px]" style={{ color: ref ? "var(--ink-3)" : "var(--warn)" }}>{ref ? "ref" : "est."}</span>
              </label>
            );
          })}
          <p className="pt-1 text-ink-3">“est.” marks tuned or free parameters, which are not measurements.</p>
        </div>
      </details>
      <button className="btn btn-primary btn-block" onClick={create} disabled={busy || (mode === "circuit" && !sel.group && !sel.root_ids?.length && !sel.cell_types?.length) || (mode === "region" && !regions.length)}>
        {busy ? "Working…" : hasSession ? "Replace session" : "Create session"}
      </button>
    </div>
  );
}

function StimulusPanel({ session, act }: { session: SimSummary; act: (fn: () => Promise<SimSummary>) => Promise<SimSummary | null> }) {
  const [spec, setSpec] = useState<StimulusSpec>({ kind: "poisson", selector: {}, rate_hz: 150, frequency_hz: 50, amplitude_mV: 10, start_ms: 0, stop_ms: 500, repeats: 1, interval_ms: 0 });
  const [relative, setRelative] = useState(true);
  return (
    <div className="space-y-4 text-xs">
      <SelectorInput datasetId={session.dataset_id} value={spec.selector} onChange={(s) => setSpec({ ...spec, selector: s })} />
      <div className="grid grid-cols-2 gap-3">
        <Field className="col-span-2" label="Type" hint="Poisson spikes approximate optogenetic activation (the reference method). A pulse train is frequency-locked. Current is injected drive, a FlyMind extension.">
          <select className="input" value={spec.kind} onChange={(e) => setSpec({ ...spec, kind: e.target.value as StimulusSpec["kind"] })}>
            <option value="poisson">Poisson spikes</option><option value="pulse_train">Pulse train</option><option value="current">Current (mV drive)</option>
          </select>
        </Field>
        {spec.kind === "poisson" && <Field label="Rate" unit="Hz"><input type="number" className="input" value={spec.rate_hz} onChange={(e) => setSpec({ ...spec, rate_hz: +e.target.value })} /></Field>}
        {spec.kind === "pulse_train" && <Field label="Frequency" unit="Hz"><input type="number" className="input" value={spec.frequency_hz} onChange={(e) => setSpec({ ...spec, frequency_hz: +e.target.value })} /></Field>}
        {spec.kind === "current" && <Field label="Amplitude" unit="mV"><input type="number" className="input" value={spec.amplitude_mV} onChange={(e) => setSpec({ ...spec, amplitude_mV: +e.target.value })} /></Field>}
        <Field label="Start" unit="ms"><input type="number" className="input" value={spec.start_ms} onChange={(e) => setSpec({ ...spec, start_ms: +e.target.value })} /></Field>
        <Field label="Stop (ms)" hint="Leave blank to stimulate until the run ends"><input type="number" className="input" placeholder="open-ended" value={spec.stop_ms ?? ""} onChange={(e) => setSpec({ ...spec, stop_ms: e.target.value === "" ? null : +e.target.value })} /></Field>
        <Field label="Repeats"><input type="number" min={1} className="input" value={spec.repeats} onChange={(e) => setSpec({ ...spec, repeats: +e.target.value })} /></Field>
        <Field label="Interval" unit="ms"><input type="number" min={0} className="input" value={spec.interval_ms} onChange={(e) => setSpec({ ...spec, interval_ms: +e.target.value })} /></Field>
      </div>
      <label className="check"><input type="checkbox" checked={relative} onChange={(e) => setRelative(e.target.checked)} /><span>Times are relative to now (t = <span className="mono">{fmt.ms(session.t_ms)}</span>)</span></label>
      <button className="btn btn-block" disabled={!spec.selector.group && !spec.selector.root_ids?.length && !spec.selector.cell_types?.length}
        onClick={() => act(() => api.addStimulus(session.id, { ...spec, relative, label: spec.selector.group ?? spec.selector.cell_types?.join(",") ?? `${spec.selector.root_ids?.length} neurons` }))}><Icon name="plus" size={14} />Add stimulus</button>
      <ul data-testid="stimulus-list" className="-mt-1">
        {session.stimuli.map((s) => (
          <li key={s.id} className="flex items-start gap-2 border-t border-rule py-2">
            <span className="flex-1 leading-5"><span className="text-ink">{s.label || s.kind}</span><br /><span className="mono text-[11px] text-ink-3">{s.kind === "poisson" ? `${s.rate_hz} Hz` : s.kind === "pulse_train" ? `${s.frequency_hz} Hz pulses` : `${s.amplitude_mV} mV`}, {s.start_ms} to {s.stop_ms ?? "end"} ms{(s.repeats ?? 1) > 1 ? `, ${s.repeats} repeats` : ""}</span></span>
            <button className="btn btn-icon btn-sm btn-quiet" aria-label="Remove stimulus" data-tip="Remove" onClick={() => act(() => api.removeStimulus(session.id, s.id))}><Icon name="close" size={12} /></button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function InterventionPanel({ session, act }: { session: SimSummary; act: (fn: () => Promise<SimSummary>) => Promise<SimSummary | null> }) {
  const [spec, setSpec] = useState<InterventionSpec>({ kind: "silence", selector: {}, mode: "block_output", factor: 0 });
  const [post, setPost] = useState<Selector>({});
  return (
    <div className="space-y-4 text-xs">
      <SelectorInput datasetId={session.dataset_id} value={spec.selector} onChange={(s) => setSpec({ ...spec, selector: s })} />
      <select className="input" aria-label="Intervention type" value={spec.kind === "silence" ? spec.mode : "scale"} onChange={(e) => setSpec(e.target.value === "scale" ? { ...spec, kind: "synaptic_scaling" } : { ...spec, kind: "silence", mode: e.target.value as "block_output" | "clamp" })}>
        <option value="block_output">Silence: block synaptic output (like tetanus toxin; reference method)</option>
        <option value="clamp">Silence: clamp at rest, no spikes (like Kir2.1)</option>
        <option value="scale">Scale outgoing connections (reversible lesion)</option>
      </select>
      {spec.kind === "synaptic_scaling" && (
        <>
          <Slider label="Scaling factor" value={spec.factor ?? 0} min={0} max={2} step={0.05} onChange={(v) => setSpec({ ...spec, factor: v })} format={(v) => v.toFixed(2)} />
          <p className="text-ink-3">Optionally restrict the change to selected targets.</p>
          <SelectorInput datasetId={session.dataset_id} value={post} onChange={setPost} />
        </>
      )}
      <button className="btn btn-block" disabled={!spec.selector.group && !spec.selector.root_ids?.length && !spec.selector.cell_types?.length}
        onClick={() => act(() => api.addIntervention(session.id, { ...spec, post_selector: spec.kind === "synaptic_scaling" && (post.group || post.root_ids?.length || post.cell_types?.length) ? post : null, label: spec.selector.group ?? spec.selector.cell_types?.join(",") ?? `${spec.selector.root_ids?.length} neurons` }))}>Apply intervention</button>
      <ul data-testid="intervention-list" className="-mt-1">
        {session.interventions.map((s) => (
          <li key={s.id} className="flex items-start gap-2 border-t border-rule py-2">
            <span className="flex-1 leading-5"><span className="text-ink">{s.label}</span><br /><span className="mono text-[11px] text-ink-3">{s.kind === "silence" ? s.mode : `scaled by ${s.factor}`}</span></span>
            <button className="btn btn-icon btn-sm btn-quiet" aria-label="Remove intervention" data-tip="Remove" onClick={() => act(() => api.removeIntervention(session.id, s.id))}><Icon name="close" size={12} /></button>
          </li>
        ))}
      </ul>
      {session.interventions.length > 0 && <button className="btn btn-block" onClick={() => act(() => api.clearInterventions(session.id))}>Restore original connectome</button>}
      <p className="text-ink-3">Interventions never change the stored connectome. Weights are recomputed from the original synapse counts.</p>
    </div>
  );
}

interface SpikeBuf { t: number[]; idx: number[] }

function Running({ session, act, err, onPickNeuron }: { session: SimSummary; act: (fn: () => Promise<SimSummary>) => Promise<SimSummary | null>; err: Error | null; onPickNeuron: (rid: string) => void }) {
  const colors = useChartColors();
  const [live, setLive] = useState<{ t_ms: number; ratio: number | null; wall: number; total: number; truncated: boolean }>({ t_ms: session.t_ms, ratio: session.sim_wall_ratio, wall: session.wall_running_s, total: session.n_spikes, truncated: false });
  const buf = useRef<SpikeBuf>({ t: [], idx: [] });
  const [rasterTick, setRasterTick] = useState(0);
  const [activity, setActivity] = useState<Activity | null>(null);
  const [snapshot, setSnapshot] = useState<Activity | null>(null);
  const [pop, setPop] = useState<Record<string, { t_ms: number[]; rate_hz: number[]; n_neurons: number }>>({});
  const [traces, setTraces] = useState<{ root_ids: string[]; t_ms: number[]; v_mV: number[][] } | null>(null);
  const [steps, setSteps] = useState(100);
  const [scrubEnd, setScrubEnd] = useState<number | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const running = session.status === "running";
  useEffect(() => { setLive((l) => ({ ...l, total: Math.max(l.total, session.n_spikes), t_ms: Math.max(l.t_ms, session.t_ms) })); }, [session.n_spikes, session.t_ms]);
  // When not running, show recorded spikes from the server (scrub through the session).
  useEffect(() => {
    if (running) { setScrubEnd(null); return; }
    if (session.t_ms <= 0) return;
    if (scrubEnd === null) {
      // default: the window ending just after the most recent spike
      api.raster(session.id, 0, session.t_ms, undefined, 1).then((r) => {
        const last = r.t_ms.length ? r.t_ms[r.t_ms.length - 1] : session.t_ms;
        setScrubEnd(Math.min(session.t_ms, Math.max(RASTER_WINDOW_MS, Math.ceil((last + 20) / 10) * 10)));
      }).catch(() => undefined);
      return;
    }
    const end = scrubEnd;
    api.raster(session.id, Math.max(0, end - RASTER_WINDOW_MS), end).then((r) => {
      buf.current = { t: r.t_ms, idx: r.idx };
      setRasterTick((x) => x + 1);
    }).catch(() => undefined);
  }, [running, scrubEnd, session.id, session.t_ms]);

  const statusRef = useRef(session.status);
  statusRef.current = session.status;
  useEffect(() => {
    buf.current = { t: [], idx: [] };
    const ws = new WebSocket(wsUrl(`/ws/sim/${session.id}`));
    ws.onopen = () => ws.send(JSON.stringify({ interval_ms: 100, max_spikes: 20000 }));
    ws.onmessage = (ev) => {
      const f = JSON.parse(ev.data) as SimFrame;
      if (f.type === "frame") {
        const b = buf.current;
        b.t.push(...(f.spike_t_ms ?? []));
        b.idx.push(...(f.spike_idx ?? []));
        const cut = (f.t_ms ?? 0) - RASTER_WINDOW_MS;
        let k = 0;
        while (k < b.t.length && b.t[k] < cut) k++;
        if (k) { b.t.splice(0, k); b.idx.splice(0, k); }
        setLive({ t_ms: f.t_ms ?? 0, ratio: f.sim_wall_ratio ?? null, wall: f.wall_running_s ?? 0, total: f.n_spikes_total ?? 0, truncated: !!f.truncated });
        setRasterTick((x) => x + 1);
      }
      if ((f.type === "status" || f.type === "frame") && f.status && f.status !== statusRef.current) {
        statusRef.current = f.status;
        act(() => api.sim(session.id));
      }
    };
    return () => ws.close();
  }, [session.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = useCallback(() => {
    const groups = session.stimuli.map((s) => `stim:${s.id}`);
    if (groups.length) api.population(session.id, groups, 10).then((r) => setPop(r.groups)).catch(() => undefined);
    api.activity(session.id, Math.max(0, live.t_ms - 200), live.t_ms || undefined).then(setActivity).catch(() => undefined);
    if (session.probe_root_ids.length) api.traces(session.id).then(setTraces).catch(() => undefined);
  }, [session, live.t_ms]);
  useInterval(refresh, running ? 1000 : null);
  useEffect(() => { refresh(); }, [session.status, session.stimuli.length, session.probe_root_ids.length]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.code !== "Space" || ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(t.tagName)) return;
      e.preventDefault();
      act(() => api.control(session.id, session.status === "running" ? "pause" : session.status === "paused" ? "resume" : "start"));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [session.id, session.status, act]);

  const raster = useMemo(() => {
    const b = buf.current;
    const order = Array.from(new Set(b.idx)).sort((a, c) => a - c);
    const rank = new Map(order.map((v, i) => [v, i]));
    return { x: b.t.slice(), y: b.idx.map((i) => rank.get(i) ?? 0), ids: b.idx.slice(), n: order.length };
  }, [rasterTick]);  // eslint-disable-line react-hooks/exhaustive-deps

  const t = running ? (live.t_ms || session.t_ms) : (scrubEnd ?? session.t_ms);
  const ctl = (action: string, extra: Record<string, unknown> = {}) => act(() => api.control(session.id, action, extra));
  const finished = ["finished", "stopped"].includes(session.status);
  const toggle = running ? { label: "Pause", icon: "pause" as const, run: () => ctl("pause"), disabled: false }
    : session.status === "paused" ? { label: "Resume", icon: "play" as const, run: () => ctl("resume"), disabled: false }
    : { label: "Start", icon: "play" as const, run: () => ctl("start"), disabled: finished };
  const savedNote = saved && <Notice tone="accent" role="status" className="mt-3 !text-xs">{saved}</Notice>;
  return (
    <>
      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-rule bg-paper px-6 py-2" role="toolbar" aria-label="Simulation controls">
          <button className="btn btn-primary" onClick={toggle.run} disabled={toggle.disabled}><Icon name={toggle.icon} size={14} />{toggle.label}</button>
          <button className="btn" onClick={() => ctl("step", { n_steps: steps })} disabled={running || finished}><Icon name="step" size={14} />Step</button>
          <select className="input !w-28" aria-label="Step size" value={steps} onChange={(e) => setSteps(+e.target.value)}>
            {[1, 10, 100, 1000].map((n) => <option key={n} value={n}>{n.toLocaleString()} {n === 1 ? "step" : "steps"}</option>)}
          </select>
          <span aria-hidden className="mx-2 h-5 w-px bg-rule-strong" />
          <button className="btn btn-danger" onClick={() => ctl("stop")} disabled={finished}><Icon name="stop" size={14} />Stop</button>
          <button className="btn" onClick={() => ctl("reset", { seed: session.seed })}><Icon name="reset" size={14} />Reset</button>
          <select className="input ml-auto !w-40" aria-label="Speed" value={session.speed ?? 0} onChange={(e) => ctl("speed", { speed: +e.target.value || null })}>
            <option value={0}>Maximum speed</option><option value={1}>Real time</option><option value={0.5}>Half speed</option><option value={0.1}>One tenth</option><option value={0.02}>One fiftieth</option>
          </select>
        </div>

        <div className="space-y-10 px-6 pb-12 pt-6">
          <ErrorBox error={err ?? (session.error ? new Error(session.error) : null)} />

          <Figure n={1} caption={<>Spike raster, {RASTER_WINDOW_MS} ms window, <span className="mono">{raster.n.toLocaleString()}</span> active neurons. Click a spike to select its neuron.{live.truncated && <span style={{ color: "var(--warn)" }}> The live stream was truncated.</span>}</>}>
            {!running && session.t_ms > 0 && (
              <div className="mb-2 max-w-md">
                <Slider label="Raster window end" value={scrubEnd ?? session.t_ms} min={Math.min(RASTER_WINDOW_MS, session.t_ms)} max={session.t_ms} step={10} onChange={setScrubEnd} format={(v) => fmt.ms(v)} />
              </div>
            )}
            {raster.x.length === 0 ? <Empty title={session.t_ms > 0 ? "No spikes in this window." : "No spikes yet."}>{session.t_ms > 0 ? "Move the window to a stimulated period." : "Add a stimulus, then start the simulation."}</Empty> : (
              <Plot testId="raster" height={300} onClick={(p) => api.neuronAt(session.dataset_id, p.customdata as number).then((n) => onPickNeuron(n.root_id))}
                data={[{ type: "scattergl", mode: "markers", x: raster.x, y: raster.y, customdata: raster.ids, marker: { size: 2.5, color: colors.accent }, hovertemplate: "t = %{x:.1f} ms<br>neuron index %{customdata}<extra></extra>" }]}
                layout={{ xaxis: { title: { text: "time (ms)" }, range: [Math.max(0, t - RASTER_WINDOW_MS), t] }, yaxis: { title: { text: "active neuron, ranked" } }, showlegend: false }} />
            )}
          </Figure>

          <div className="grid gap-x-10 gap-y-10 min-[1800px]:grid-cols-2">
            <Figure n={2} caption="Population firing rate of each stimulated group, 10 ms bins.">
              {Object.keys(pop).length === 0 ? <Empty title="No stimulated groups." /> : (
                <Plot testId="population" height={240} endLabels
                  data={Object.entries(pop).map(([k, v], i) => ({ type: "scatter", mode: "lines", name: session.stimuli.find((s) => `stim:${s.id}` === k)?.label ?? k, x: v.t_ms, y: v.rate_hz, line: { width: 1.5, color: colors.palette[i % colors.palette.length] } }))}
                  layout={{ xaxis: { title: { text: "time (ms)" } }, yaxis: { title: { text: "Hz per neuron" } } }} />
              )}
            </Figure>
            <Figure n={3} caption={<>Membrane potential of probed neurons, in model units. Add a probe with Record trace in the explorer, or from the table on the right.{session.probe_root_ids.length > 0 && <> <button className="btn btn-link text-xs" onClick={() => act(() => api.setProbes(session.id, []))}>Clear probes</button></>}</>}>
              {!traces || !traces.root_ids.length ? <Empty title="No probes.">Select neurons to record their simulated membrane potential.</Empty> : (
                <Plot testId="traces" height={240} endLabels
                  data={traces.v_mV.map((v, i) => ({ type: "scatter", mode: "lines", name: traces.root_ids[i].slice(-6), x: traces.t_ms, y: v, line: { width: 1, color: colors.palette[i % colors.palette.length] } }))}
                  layout={{ xaxis: { title: { text: "time (ms)" } }, yaxis: { title: { text: "v (mV)" } } }} />
              )}
            </Figure>
            <Figure n={4} className="min-[1800px]:col-span-2" caption={<>Mean rate per neuron in the 15 most active regions over the last 200 ms.
              <span className="ml-3 inline-flex items-center gap-3 align-baseline">
                <button className="btn btn-link text-xs" onClick={() => setSnapshot(activity)} disabled={!activity}>Keep as “before”</button>
                {snapshot && <button className="btn btn-link text-xs" onClick={() => setSnapshot(null)}>Clear</button>}
              </span></>}>
              {!activity || activity.regions.length === 0 ? <Empty title="No activity in this window." /> : (
                <Plot testId="regions" height={240}
                  data={[
                    ...(snapshot ? [{ type: "bar" as const, name: "before", x: snapshot.regions.slice(0, 15).map((r) => r.label), y: snapshot.regions.slice(0, 15).map((r) => r.mean_rate_hz), marker: { color: colors.neutral } }] : []),
                    { type: "bar" as const, name: snapshot ? "now" : "mean rate", x: activity.regions.slice(0, 15).map((r) => r.label), y: activity.regions.slice(0, 15).map((r) => r.mean_rate_hz), marker: { color: colors.accent } },
                  ]}
                  layout={{ barmode: "group", bargap: 0.35, yaxis: { title: { text: "mean Hz per neuron" } }, showlegend: !!snapshot }} />
              )}
            </Figure>
          </div>
        </div>
      </div>

      <aside aria-label="Session" className="inspector">
        <Block title="Session" right={<EvidenceBadge kind={session.evidence} />}>
          <div className="mono mb-3 text-xs text-ink-3">{session.id}</div>
          <KV rows={[
            ["Status", <span key="s" data-testid="sim-status">{session.status}</span>],
            ["Simulated time", <span key="t" data-testid="sim-time">{fmt.ms(t)}</span>],
            [<span key="w" title="Measured wall-clock time spent integrating">Wall time</span>, live.wall.toFixed(2), "s"],
            [<span key="r" title="Simulated seconds per wall-clock second over recent chunks. Not real time unless at least 1.">Simulated per wall second</span>, live.ratio ? live.ratio.toFixed(2) : "–", "×"],
            ["Spikes", fmt.int(live.total)],
            ["Network", `${session.n_neurons.toLocaleString()} neurons, ${session.mode}`],
            ["Seed", String(session.seed)],
          ]} />
        </Block>
        <Block title="Keep">
          <div className="flex flex-wrap gap-2">
            <a className="btn btn-sm no-underline hover:text-ink" href={api.exportUrl(session.id, "parquet")}><Icon name="download" size={12} />Parquet</a>
            <a className="btn btn-sm no-underline hover:text-ink" href={api.exportUrl(session.id, "csv")}><Icon name="download" size={12} />CSV</a>
            <a className="btn btn-sm no-underline hover:text-ink" href={api.exportUrl(session.id, "json")}><Icon name="download" size={12} />JSON</a>
            <button className="btn btn-sm" onClick={() => api.saveSim(session.id).then((r) => setSaved(`Saved as experiment ${r.experiment_id}`))}><Icon name="save" size={12} />Save as experiment</button>
          </div>
          {savedNote}
        </Block>
        {activity && activity.top.length > 0 && (
          <Block title="Most active neurons" right={<span className="text-xs text-ink-3">last 200 ms</span>}>
            <div className="-mx-1 max-h-[26rem] overflow-y-auto px-1">
              <table className="tbl">
                <thead><tr><th>Neuron</th><th className="num">Hz</th><th /></tr></thead>
                <tbody>
                  {activity.top.slice(0, 40).map((n) => (
                    <tr key={n.idx}>
                      <td><div>{n.cell_type ?? "–"}</div><div className="mono text-[11px] text-ink-3">{n.root_id}</div></td>
                      <td className="num">{n.rate_hz.toFixed(1)}</td>
                      <td className="whitespace-nowrap text-right">
                        <button className="btn btn-link text-xs" onClick={() => onPickNeuron(n.root_id)}>Select</button>
                        <button className="btn btn-link ml-3 text-xs" onClick={() => act(() => api.setProbes(session.id, Array.from(new Set([...session.probe_root_ids, n.root_id])).slice(0, 64)))}>Trace</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-ink-3">All values are simulation output of the leaky integrate-and-fire model, not recorded activity.</p>
          </Block>
        )}
      </aside>
    </>
  );
}
