import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { STATIC_DEMO, api, wsUrl } from "../lib/api";
import { useApp } from "../lib/store";
import type { Activity, InterventionSpec, Selector, SimFrame, SimSummary, StimulusSpec } from "../lib/types";
import { Plot } from "../components/Plot";
import { Empty, ErrorBox, EvidenceBadge, Field, Section, SelectorInput, Stat, SyntheticBanner, fmt, useAsync, useDatasets, useInterval } from "../components/ui";
import { categoryColor } from "../lib/colors";

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
    return <div className="p-6"><Empty title="The Brain Simulator needs the local backend">The LIF engine runs in Python (Numba/Brian2). Run <code className="mono">make dev</code> locally to use it.</Empty></div>;
  }

  return (
    <div className="grid h-full grid-cols-[22rem_1fr] gap-3 p-3">
      <div className="space-y-3 overflow-y-auto">
        <SyntheticBanner show={!!meta?.synthetic} />
        {pending && (!session || pending.datasetId !== session.dataset_id) && (
          <div role="status" className="rounded-lg border border-accent/40 bg-accent/10 px-3 py-2 text-xs text-accent">
            Pending from Explorer: {pending.kind} {pending.label} ({pending.rootIds.length} neuron{pending.rootIds.length > 1 ? "s" : ""}). Create a session to apply it.
          </div>
        )}
        <SetupPanel datasetId={datasetId} hasSession={!!session} onCreate={(cfg) => act(async () => {
          if (session) await api.deleteSim(session.id).catch(() => undefined);
          const s = await api.createSim(cfg);
          setSimSessionId(s.id);
          return s;
        })} busy={busy} />
        {session && <StimulusPanel session={session} act={act} />}
        {session && <InterventionPanel session={session} act={act} />}
      </div>
      <div className="min-w-0 space-y-3 overflow-y-auto">
        <ErrorBox error={err} />
        {!session ? (
          <Empty title="No simulation session">Configure a network on the left and press <b>Create session</b>. Demo mode runs the small synthetic network; full-brain mode uses the imported FlyWire dataset.</Empty>
        ) : (
          <Running session={session} act={act} onPickNeuron={(rid) => api.neuron(session.dataset_id, rid).then(setSelected)} />
        )}
      </div>
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
  return (
    <Section title="Network & model">
      <div className="space-y-2 text-sm">
        <div className="grid grid-cols-4 gap-1" role="radiogroup" aria-label="Simulation mode">
          {(["full", "circuit", "region", "demo"] as Mode[]).map((m) => (
            <button key={m} role="radio" aria-checked={mode === m} className={`btn px-1 py-1 text-xs ${mode === m ? "btn-primary" : ""}`} onClick={() => setMode(m)}
              disabled={(m === "demo") !== !!meta?.synthetic && (m === "demo" || m === "region")}
              title={{ full: "Entire imported graph", circuit: "Selected neurons (+k-hop neighbourhood)", region: "Neurons whose primary neuropil is selected", demo: "Synthetic fixture only" }[m]}>
              {m}
            </button>
          ))}
        </div>
        {mode === "full" && <p className="text-xs text-ink-400">{meta ? `${meta.n_neurons.toLocaleString()} neurons, ${meta.n_edges.toLocaleString()} connections from ${meta.synthetic ? "the synthetic fixture" : `${meta.name} v${meta.version}`}.` : ""}</p>}
        {mode === "circuit" && (
          <>
            <SelectorInput datasetId={datasetId} value={sel} onChange={setSel} />
            <Field label={`Expand neighbourhood: ${depth} hop(s)`} hint="Adds up/downstream partners with ≥5 synapses">
              <input type="range" min={0} max={3} value={depth} onChange={(e) => setDepth(+e.target.value)} className="w-full" />
            </Field>
          </>
        )}
        {mode === "region" && (
          <Field label="Neuropils" hint="Neurons are assigned to their primary (most output synapses) neuropil">
            <select multiple aria-label="Neuropils" className="input h-28" value={regions} onChange={(e) => setRegions(Array.from(e.target.selectedOptions).map((o) => o.value))}>
              {(neuropils.data?.centroids ?? []).sort((a, b) => a.neuropil.localeCompare(b.neuropil)).map((c) => <option key={c.neuropil} value={c.neuropil}>{c.neuropil} ({c.neurons})</option>)}
            </select>
          </Field>
        )}
        <div className="grid grid-cols-2 gap-2">
          <Field label="Random seed"><input type="number" className="input" value={seed} min={0} onChange={(e) => setSeed(+e.target.value)} /></Field>
          <Field label="Max duration (ms)"><input type="number" className="input" value={duration} min={10} max={600000} onChange={(e) => setDuration(+e.target.value)} /></Field>
        </div>
        <details className="text-xs">
          <summary className="cursor-pointer text-ink-300">Model parameters (Shiu et al. 2024 defaults)</summary>
          <div className="mt-2 space-y-1.5">
            {params.data && editable.map((k) => {
              const info = params.data!.info[k];
              return (
                <label key={k} className="flex items-center gap-2" title={`${info.description}. Source: ${info.source} [${info.status}]`}>
                  <span className="w-36 truncate">{k}</span>
                  <input type="number" step="any" className="input py-0.5" value={overrides[k] ?? (params.data!.defaults[k] as number)} onChange={(e) => setOverrides({ ...overrides, [k]: +e.target.value })} />
                  <span className={`chip ${info.status === "reference_model" ? "" : "border-amber-500/50 text-amber-200"}`}>{info.status === "reference_model" ? "ref" : "est."}</span>
                </label>
              );
            })}
            <p className="text-ink-400">dt = 0.1 ms, exact integration. “est.” marks tuned/free parameters (not measured).</p>
          </div>
        </details>
        <button className="btn btn-primary w-full" onClick={create} disabled={busy || (mode === "circuit" && !sel.group && !sel.root_ids?.length && !sel.cell_types?.length) || (mode === "region" && !regions.length)}>
          {busy ? "Working…" : hasSession ? "Replace session" : "Create session"}
        </button>
      </div>
    </Section>
  );
}

function StimulusPanel({ session, act }: { session: SimSummary; act: (fn: () => Promise<SimSummary>) => Promise<SimSummary | null> }) {
  const [spec, setSpec] = useState<StimulusSpec>({ kind: "poisson", selector: {}, rate_hz: 150, frequency_hz: 50, amplitude_mV: 10, start_ms: 0, stop_ms: 500, repeats: 1, interval_ms: 0 });
  const [relative, setRelative] = useState(true);
  return (
    <Section title="Stimulation">
      <div className="space-y-2 text-xs">
        <SelectorInput datasetId={session.dataset_id} value={spec.selector} onChange={(s) => setSpec({ ...spec, selector: s })} />
        <div className="grid grid-cols-2 gap-2">
          <Field label="Type" hint="Poisson ≈ optogenetic activation (reference method); pulse train = frequency-locked; current = injected drive (FlyMind extension)">
            <select className="input" value={spec.kind} onChange={(e) => setSpec({ ...spec, kind: e.target.value as StimulusSpec["kind"] })}>
              <option value="poisson">Poisson spikes</option><option value="pulse_train">Pulse train</option><option value="current">Current (mV drive)</option>
            </select>
          </Field>
          {spec.kind === "poisson" && <Field label="Rate (Hz)"><input type="number" className="input" value={spec.rate_hz} onChange={(e) => setSpec({ ...spec, rate_hz: +e.target.value })} /></Field>}
          {spec.kind === "pulse_train" && <Field label="Frequency (Hz)"><input type="number" className="input" value={spec.frequency_hz} onChange={(e) => setSpec({ ...spec, frequency_hz: +e.target.value })} /></Field>}
          {spec.kind === "current" && <Field label="Amplitude (mV)"><input type="number" className="input" value={spec.amplitude_mV} onChange={(e) => setSpec({ ...spec, amplitude_mV: +e.target.value })} /></Field>}
          <Field label="Start (ms)"><input type="number" className="input" value={spec.start_ms} onChange={(e) => setSpec({ ...spec, start_ms: +e.target.value })} /></Field>
          <Field label="Stop (ms, blank = ∞)"><input type="number" className="input" value={spec.stop_ms ?? ""} onChange={(e) => setSpec({ ...spec, stop_ms: e.target.value === "" ? null : +e.target.value })} /></Field>
          <Field label="Repeats"><input type="number" min={1} className="input" value={spec.repeats} onChange={(e) => setSpec({ ...spec, repeats: +e.target.value })} /></Field>
          <Field label="Interval (ms)"><input type="number" min={0} className="input" value={spec.interval_ms} onChange={(e) => setSpec({ ...spec, interval_ms: +e.target.value })} /></Field>
        </div>
        <label className="flex items-center gap-2"><input type="checkbox" checked={relative} onChange={(e) => setRelative(e.target.checked)} /> Times relative to now (t = {fmt.ms(session.t_ms)})</label>
        <button className="btn btn-primary w-full" disabled={!spec.selector.group && !spec.selector.root_ids?.length && !spec.selector.cell_types?.length}
          onClick={() => act(() => api.addStimulus(session.id, { ...spec, relative, label: spec.selector.group ?? spec.selector.cell_types?.join(",") ?? `${spec.selector.root_ids?.length} neurons` }))}>Add stimulus</button>
        <ul className="space-y-1" data-testid="stimulus-list">
          {session.stimuli.map((s) => (
            <li key={s.id} className="flex items-center gap-2 rounded border border-ink-700 px-2 py-1">
              <span className="flex-1">{s.label || s.kind} · {s.kind === "poisson" ? `${s.rate_hz} Hz` : s.kind === "pulse_train" ? `${s.frequency_hz} Hz pulses` : `${s.amplitude_mV} mV`} · {s.start_ms}–{s.stop_ms ?? "∞"} ms{(s.repeats ?? 1) > 1 ? ` ×${s.repeats}` : ""}</span>
              <button className="btn btn-danger px-1.5 py-0 text-[11px]" aria-label="Remove stimulus" onClick={() => act(() => api.removeStimulus(session.id, s.id))}>✕</button>
            </li>
          ))}
        </ul>
      </div>
    </Section>
  );
}

function InterventionPanel({ session, act }: { session: SimSummary; act: (fn: () => Promise<SimSummary>) => Promise<SimSummary | null> }) {
  const [spec, setSpec] = useState<InterventionSpec>({ kind: "silence", selector: {}, mode: "block_output", factor: 0 });
  const [post, setPost] = useState<Selector>({});
  return (
    <Section title="Silencing & perturbation">
      <div className="space-y-2 text-xs">
        <SelectorInput datasetId={session.dataset_id} value={spec.selector} onChange={(s) => setSpec({ ...spec, selector: s })} />
        <select className="input" aria-label="Intervention type" value={spec.kind === "silence" ? spec.mode : "scale"} onChange={(e) => setSpec(e.target.value === "scale" ? { ...spec, kind: "synaptic_scaling" } : { ...spec, kind: "silence", mode: e.target.value as "block_output" | "clamp" })}>
          <option value="block_output">Silence: block synaptic output (≈ tetanus toxin; reference method)</option>
          <option value="clamp">Silence: clamp at rest, no spikes (≈ Kir2.1)</option>
          <option value="scale">Scale outgoing connections (reversible lesion)</option>
        </select>
        {spec.kind === "synaptic_scaling" && (
          <>
            <Field label={`Factor ${spec.factor?.toFixed(2)}`}><input type="range" min={0} max={2} step={0.05} value={spec.factor} onChange={(e) => setSpec({ ...spec, factor: +e.target.value })} className="w-full" /></Field>
            <p className="text-ink-400">Optional: restrict to targets</p>
            <SelectorInput datasetId={session.dataset_id} value={post} onChange={setPost} />
          </>
        )}
        <button className="btn w-full" disabled={!spec.selector.group && !spec.selector.root_ids?.length && !spec.selector.cell_types?.length}
          onClick={() => act(() => api.addIntervention(session.id, { ...spec, post_selector: spec.kind === "synaptic_scaling" && (post.group || post.root_ids?.length || post.cell_types?.length) ? post : null, label: spec.selector.group ?? spec.selector.cell_types?.join(",") ?? `${spec.selector.root_ids?.length} neurons` }))}>Apply intervention</button>
        <ul className="space-y-1" data-testid="intervention-list">
          {session.interventions.map((s) => (
            <li key={s.id} className="flex items-center gap-2 rounded border border-ink-700 px-2 py-1">
              <span className="flex-1">{s.label} · {s.kind === "silence" ? s.mode : `×${s.factor}`}</span>
              <button className="btn btn-danger px-1.5 py-0 text-[11px]" aria-label="Remove intervention" onClick={() => act(() => api.removeIntervention(session.id, s.id))}>✕</button>
            </li>
          ))}
        </ul>
        {session.interventions.length > 0 && <button className="btn w-full" onClick={() => act(() => api.clearInterventions(session.id))}>Restore original connectome</button>}
        <p className="text-ink-400">Interventions never modify the stored connectome; weights are recomputed from the original synapse counts.</p>
      </div>
    </Section>
  );
}

interface SpikeBuf { t: number[]; idx: number[] }

function Running({ session, act, onPickNeuron }: { session: SimSummary; act: (fn: () => Promise<SimSummary>) => Promise<SimSummary | null>; onPickNeuron: (rid: string) => void }) {
  const [live, setLive] = useState<{ t_ms: number; ratio: number | null; wall: number; total: number; truncated: boolean }>({ t_ms: session.t_ms, ratio: session.sim_wall_ratio, wall: session.wall_running_s, total: session.n_spikes, truncated: false });
  const buf = useRef<SpikeBuf>({ t: [], idx: [] });
  const [rasterTick, setRasterTick] = useState(0);
  const [activity, setActivity] = useState<Activity | null>(null);
  const [snapshot, setSnapshot] = useState<Activity | null>(null);
  const [pop, setPop] = useState<Record<string, { t_ms: number[]; rate_hz: number[]; n_neurons: number }>>({});
  const [traces, setTraces] = useState<{ root_ids: string[]; t_ms: number[]; v_mV: number[][] } | null>(null);
  const [steps, setSteps] = useState(100);
  const [scrubEnd, setScrubEnd] = useState<number | null>(null);
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
  return (
    <>
      <Section title="Session" right={<div className="flex items-center gap-2"><EvidenceBadge kind={session.evidence} /><span className="chip mono">{session.id}</span></div>}>
        <div className="flex flex-wrap items-center gap-1.5" role="toolbar" aria-label="Simulation controls">
          <button className="btn btn-primary" onClick={() => ctl("start")} disabled={running || session.status === "paused" || ["finished", "stopped"].includes(session.status)}>▶ Start</button>
          <button className="btn" onClick={() => ctl("pause")} disabled={!running}>❚❚ Pause</button>
          <button className="btn" onClick={() => ctl("resume")} disabled={session.status !== "paused"}>▶ Resume</button>
          <button className="btn" onClick={() => ctl("step", { n_steps: steps })} disabled={running || ["finished", "stopped"].includes(session.status)}>Step</button>
          <select className="input w-24 py-1 text-xs" aria-label="Steps per step" value={steps} onChange={(e) => setSteps(+e.target.value)}>
            {[1, 10, 100, 1000].map((n) => <option key={n} value={n}>{n} × dt</option>)}
          </select>
          <button className="btn btn-danger" onClick={() => ctl("stop")} disabled={["stopped", "finished"].includes(session.status)}>■ Stop</button>
          <button className="btn" onClick={() => ctl("reset", { seed: session.seed })}>↺ Reset</button>
          <select className="input w-36 py-1 text-xs" aria-label="Speed" value={session.speed ?? 0} onChange={(e) => ctl("speed", { speed: +e.target.value || null })}>
            <option value={0}>Max speed</option><option value={1}>1× real time</option><option value={0.5}>0.5×</option><option value={0.1}>0.1×</option><option value={0.02}>0.02×</option>
          </select>
          <div className="ml-auto flex gap-1">
            <a className="btn text-xs" href={api.exportUrl(session.id, "parquet")}>Export parquet</a>
            <a className="btn text-xs" href={api.exportUrl(session.id, "csv")}>CSV</a>
            <a className="btn text-xs" href={api.exportUrl(session.id, "json")}>JSON</a>
            <button className="btn text-xs" onClick={() => api.saveSim(session.id).then((r) => alert(`Saved as experiment ${r.experiment_id}`))}>Save experiment</button>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-6">
          <Stat label="Status" value={<span data-testid="sim-status">{session.status}</span>} />
          <Stat label="Simulated time" value={<span data-testid="sim-time">{fmt.ms(t)}</span>} />
          <Stat label="Wall time (running)" value={`${live.wall.toFixed(2)} s`} hint="Measured wall-clock time spent integrating" />
          <Stat label="Sim / wall" value={live.ratio ? `${live.ratio.toFixed(2)}×` : "–"} hint="Simulated seconds per wall-clock second (recent chunks). Not real time unless ≥1." />
          <Stat label="Spikes" value={fmt.int(live.total)} />
          <Stat label="Network" value={`${session.n_neurons.toLocaleString()} n · ${session.mode}`} />
        </div>
        {session.error && <ErrorBox error={new Error(session.error)} />}
      </Section>
      <div className="grid gap-3 xl:grid-cols-2">
        <Section title={`Spike raster (${RASTER_WINDOW_MS} ms window, ${raster.n} active neurons)`} right={live.truncated ? <span className="chip text-amber-300">stream truncated</span> : null}>
          {!running && session.t_ms > 0 && (
            <label className="mb-1 flex items-center gap-2 text-[11px] text-ink-400">Window end
              <input aria-label="Raster window end" type="range" className="flex-1" min={Math.min(RASTER_WINDOW_MS, session.t_ms)} max={session.t_ms} step={10}
                value={scrubEnd ?? session.t_ms} onChange={(e) => setScrubEnd(+e.target.value)} />
              <span className="mono w-16 text-right">{fmt.ms(scrubEnd ?? session.t_ms)}</span>
            </label>
          )}
          {raster.x.length === 0 ? <Empty title={session.t_ms > 0 ? "No spikes in this window" : "No spikes yet"}>{session.t_ms > 0 ? "Move the window to a stimulated period." : "Add a stimulus and start the simulation."}</Empty> : (
            <Plot testId="raster" height={260} onClick={(p) => api.neuronAt(session.dataset_id, p.customdata as number).then((n) => onPickNeuron(n.root_id))}
              data={[{ type: "scattergl", mode: "markers", x: raster.x, y: raster.y, customdata: raster.ids, marker: { size: 2.5, color: "#5eead4" }, hovertemplate: "t=%{x:.1f} ms<br>idx %{customdata}<extra></extra>" }]}
              layout={{ xaxis: { title: { text: "time (ms)" }, range: [Math.max(0, t - RASTER_WINDOW_MS), t] }, yaxis: { title: { text: "active neuron (rank)" } }, showlegend: false }} />
          )}
        </Section>
        <Section title="Population firing rate of stimulated groups (10 ms bins)">
          {Object.keys(pop).length === 0 ? <Empty title="No stimulated groups" /> : (
            <Plot testId="population" height={260}
              data={Object.entries(pop).map(([k, v], i) => ({ type: "scatter", mode: "lines", name: session.stimuli.find((s) => `stim:${s.id}` === k)?.label ?? k, x: v.t_ms, y: v.rate_hz, line: { width: 1.5, color: categoryColor("x", `${i}${k}`) } }))}
              layout={{ xaxis: { title: { text: "time (ms)" } }, yaxis: { title: { text: "Hz per neuron" } } }} />
          )}
        </Section>
        <Section title="Membrane potential traces (probes)" right={<span className="text-[11px] text-ink-400">Use “Record trace” in the Explorer or click a raster point</span>}>
          {!traces || !traces.root_ids.length ? <Empty title="No probes">Select neurons to record their simulated membrane potential.</Empty> : (
            <Plot testId="traces" height={260}
              data={traces.v_mV.map((v, i) => ({ type: "scatter", mode: "lines", name: traces.root_ids[i].slice(-6), x: traces.t_ms, y: v, line: { width: 1 } }))}
              layout={{ xaxis: { title: { text: "time (ms)" } }, yaxis: { title: { text: "v (mV, model)" } } }} />
          )}
          {session.probe_root_ids.length > 0 && <button className="btn mt-1 text-xs" onClick={() => act(() => api.setProbes(session.id, []))}>Clear probes</button>}
        </Section>
        <Section title="Regional activity (last 200 ms)" right={
          <div className="flex gap-1">
            <button className="btn py-0.5 text-xs" onClick={() => setSnapshot(activity)} disabled={!activity}>Snapshot “before”</button>
            {snapshot && <button className="btn py-0.5 text-xs" onClick={() => setSnapshot(null)}>Clear</button>}
          </div>}>
          {!activity || activity.regions.length === 0 ? <Empty title="No activity in window" /> : (
            <Plot testId="regions" height={260}
              data={[
                ...(snapshot ? [{ type: "bar" as const, name: "before", x: snapshot.regions.slice(0, 15).map((r) => r.label), y: snapshot.regions.slice(0, 15).map((r) => r.mean_rate_hz), marker: { color: "#64748b" } }] : []),
                { type: "bar" as const, name: snapshot ? "now" : "mean rate", x: activity.regions.slice(0, 15).map((r) => r.label), y: activity.regions.slice(0, 15).map((r) => r.mean_rate_hz), marker: { color: "#f472b6" } },
              ]}
              layout={{ barmode: "group", yaxis: { title: { text: "mean Hz / neuron" } }, showlegend: !!snapshot }} />
          )}
        </Section>
      </div>
      {activity && activity.top.length > 0 && (
        <Section title="Most active neurons (last 200 ms)">
          <div className="max-h-64 overflow-y-auto">
            <table className="table">
              <thead><tr><th>Root ID</th><th>Cell type</th><th>Rate (Hz)</th><th /></tr></thead>
              <tbody>
                {activity.top.slice(0, 40).map((n) => (
                  <tr key={n.idx}>
                    <td className="mono">{n.root_id}</td><td>{n.cell_type ?? "—"}</td><td className="mono">{n.rate_hz.toFixed(1)}</td>
                    <td className="space-x-1 text-right">
                      <button className="btn px-1.5 py-0 text-[11px]" onClick={() => onPickNeuron(n.root_id)}>Select</button>
                      <button className="btn px-1.5 py-0 text-[11px]" onClick={() => act(() => api.setProbes(session.id, Array.from(new Set([...session.probe_root_ids, n.root_id])).slice(0, 64)))}>Trace</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-[11px] text-ink-400">All values are simulation output of the LIF model, not recorded activity.</p>
        </Section>
      )}
    </>
  );
}

