import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { STATIC_DEMO, api, decodeB64, wsUrl } from "../lib/api";
import { useApp } from "../lib/store";
import type { ArenaConfig, BridgeConfig, FlyFrame, FlySummary, SceneObject } from "../lib/types";
import { FlyScene, type PoseSource, buildFlyGeometries } from "../three/FlyScene";
import { Plot } from "../components/Plot";
import { Empty, ErrorBox, EvidenceBadge, Field, Loading, Section, Stat, fmt, useAsync, useDatasets, useInterval } from "../components/ui";

export default function VirtualFly() {
  const { datasetId } = useApp();
  const datasets = useDatasets();
  const arenas = useAsync(() => (STATIC_DEMO ? Promise.resolve([] as ArenaConfig[]) : api.arenas()), []);
  const bridges = useAsync(() => (STATIC_DEMO ? Promise.resolve([] as BridgeConfig[]) : api.bridges()), []);
  const meshes = useAsync(async () => {
    if (STATIC_DEMO) return null;
    const [meta, data] = await Promise.all([api.meshMeta(), api.meshData()]);
    return buildFlyGeometries(meta, data);
  }, []);
  const [arena, setArena] = useState<ArenaConfig | null>(null);
  const [controller, setController] = useState<"baseline" | "neural">("baseline");
  const [duration, setDuration] = useState(10);
  const [forward, setForward] = useState(1.0);
  const [turn, setTurn] = useState(0);
  const [session, setSession] = useState<FlySummary | null>(null);
  const [objects, setObjects] = useState<SceneObject[]>([]);
  const [frame, setFrame] = useState<FlyFrame | null>(null);
  const [trail, setTrail] = useState<number[][]>([]);
  const [follow, setFollow] = useState(true);
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [traj, setTraj] = useState<{ rows: Record<string, number>[]; metrics: Record<string, number> } | null>(null);
  const [replay, setReplay] = useState<{ id: string; t: number[]; poses: Float32Array; n: number; rows: Record<string, number>[] } | null>(null);
  const source = useRef<PoseSource>({ poses: null, pos: null });
  const odor = useAsync(() => (arena && !STATIC_DEMO ? api.odorField(arena) : Promise.resolve(null)), [arena]);

  useEffect(() => { if (arenas.data && !arena) setArena(arenas.data[1] ?? arenas.data[0]); }, [arenas.data, arena]);
  const ds = datasets.data?.find((d) => d.dataset_id === datasetId);
  const bridge = bridges.data?.find((b) => b.dataset_ids.includes(datasetId));

  // live stream
  useEffect(() => {
    if (!session) return;
    const ws = new WebSocket(wsUrl(`/ws/fly/${session.id}`));
    ws.onmessage = (ev) => {
      const f = JSON.parse(ev.data) as FlyFrame;
      if (f.type === "hello" && f.scene) setObjects(f.scene);
      if (f.type === "frame") {
        source.current = { poses: f.poses ?? null, pos: f.pos ?? null };
        setFrame(f);
        if (f.pos) setTrail((t) => (t.length > 3000 ? [...t.slice(-2000), f.pos!] : [...t, f.pos!]));
      }
      if (f.type === "status" && f.status && f.status !== session.status) api.fly(session.id).then(setSession).catch(() => undefined);
    };
    return () => ws.close();
  }, [session?.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const pollTraj = useCallback(() => { if (session) api.flyTrajectory(session.id).then(setTraj).catch(() => undefined); }, [session]);
  useInterval(pollTraj, session?.status === "running" ? 1500 : null);
  useEffect(() => { pollTraj(); }, [session?.status]);  // eslint-disable-line react-hooks/exhaustive-deps

  const create = async () => {
    if (!arena) return;
    setBusy(true); setErr(null); setTrail([]); setReplay(null);
    try {
      if (session) await api.flyControl(session.id, "stop").catch(() => undefined);
      const s = await api.createFly({
        arena, controller, duration_s: duration, baseline: { forward, turn },
        bridge: bridge?.name ?? "synthetic_demo",
        brain: controller === "neural" ? { dataset_id: datasetId, network: { mode: ds?.synthetic ? "demo" : "full" } } : null,
        label: `${arena.name} · ${controller}`,
      });
      setSession(s); setObjects(s.scene ?? []);
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  const ctl = (action: string) => session && api.flyControl(session.id, action).then(setSession, setErr);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.code !== "Space" || ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(t.tagName) || !session) return;
      e.preventDefault();
      ctl(session.status === "running" ? "pause" : session.status === "paused" ? "resume" : "start");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // replay playback
  useEffect(() => {
    if (!replay) return;
    let i = 0;
    const id = setInterval(() => {
      if (i >= replay.t.length) { clearInterval(id); return; }
      const poses = replay.poses.subarray(i * replay.n * 7, (i + 1) * replay.n * 7);
      const row = replay.rows[Math.min(replay.rows.length - 1, Math.floor((i / replay.t.length) * replay.rows.length))];
      source.current = { poses, pos: row ? [row.x_mm, row.y_mm, row.z_mm] : null };
      setFrame({ type: "frame", t_s: replay.t[i], pos: row ? [row.x_mm, row.y_mm, row.z_mm] : undefined, heading_rad: row?.heading_rad, ds: row ? [row.ds_left, row.ds_right] : undefined });
      i++;
    }, 1000 / 30);
    return () => clearInterval(id);
  }, [replay]);

  if (STATIC_DEMO) {
    return <div className="p-6"><Empty title="The Virtual Fly needs the local backend">MuJoCo physics (FlyGym) runs in Python; the browser only renders its state. Run <code className="mono">make dev</code> locally.</Empty></div>;
  }

  const s = frame?.sensors ?? {};
  return (
    <div className="grid h-full grid-cols-[21rem_1fr_21rem] gap-3 p-3">
      <div className="space-y-3 overflow-y-auto">
        <Section title="Environment">
          {!arenas.data ? <Loading /> : (
            <div className="space-y-2 text-sm">
              <select aria-label="Arena" className="input" value={arena?.kind ?? ""} onChange={(e) => setArena(arenas.data!.find((a) => a.kind === e.target.value) ?? null)}>
                {arenas.data.map((a) => <option key={a.kind} value={a.kind}>{a.name}</option>)}
              </select>
              <p className="text-xs text-ink-400">{arena?.description}</p>
              {arena && <ArenaEditor arena={arena} onChange={setArena} />}
            </div>
          )}
        </Section>
        <Section title="Controller">
          <div className="space-y-2 text-sm">
            <div className="grid grid-cols-2 gap-1" role="radiogroup" aria-label="Controller">
              <button role="radio" aria-checked={controller === "baseline"} className={`btn text-xs ${controller === "baseline" ? "btn-primary" : ""}`} onClick={() => setController("baseline")}>Baseline</button>
              <button role="radio" aria-checked={controller === "neural"} className={`btn text-xs ${controller === "neural" ? "btn-primary" : ""}`} onClick={() => setController("neural")}>Neural (connectome)</button>
            </div>
            {controller === "baseline" ? (
              <>
                <p className="text-xs text-ink-400">Fixed descending command into FlyGym's CPG walking controller. Verifies body mechanics independently of any neural model.</p>
                <Field label={`Forward drive ${forward.toFixed(2)}`}><input type="range" min={-1.2} max={1.2} step={0.05} value={forward} onChange={(e) => { setForward(+e.target.value); if (session?.controller === "baseline") api.flyBaseline(session.id, { forward: +e.target.value, turn }).then(setSession); }} className="w-full" /></Field>
                <Field label={`Turn ${turn.toFixed(2)} (+ = left)`}><input type="range" min={-1} max={1} step={0.05} value={turn} onChange={(e) => { setTurn(+e.target.value); if (session?.controller === "baseline") api.flyBaseline(session.id, { forward, turn: +e.target.value }).then(setSession); }} className="w-full" /></Field>
              </>
            ) : (
              <div className="space-y-1 text-xs text-ink-300">
                <p>Brain: <b>{ds?.synthetic ? "synthetic demo network" : `${ds?.name ?? datasetId} v${ds?.version ?? ""} (full brain)`}</b></p>
                {bridge ? <p>Bridge: <b>{bridge.name}</b> <EvidenceBadge kind={bridge.evidence} /></p> : <p className="text-rose-300">No neural–motor bridge is defined for this dataset.</p>}
                <p className="text-ink-400">{bridge?.description}</p>
                {!ds?.synthetic && <p className="text-amber-200">Full-brain closed loop runs well below real time (≈0.1–0.2× on a laptop CPU).</p>}
              </div>
            )}
            <Field label="Duration (s, simulated)"><input type="number" className="input" min={0.5} max={120} step={0.5} value={duration} onChange={(e) => setDuration(+e.target.value)} /></Field>
            <button className="btn btn-primary w-full" onClick={create} disabled={busy || !arena || (controller === "neural" && !bridge)}>{busy ? "Building MuJoCo model…" : "Create fly session"}</button>
          </div>
        </Section>
        <Recordings onReplay={(r) => { setSession(null); setTrail(r.rows.map((x) => [x.x_mm, x.y_mm])); setReplay(r); }} />
      </div>

      <div className="relative min-h-[520px] min-w-0 overflow-hidden rounded-xl border border-ink-800">
        {meshes.loading && <div className="absolute left-3 top-3 z-10"><Loading label="Loading NeuroMechFly meshes" /></div>}
        <ErrorBox error={meshes.error ?? err} />
        <FlyScene parts={meshes.data ?? null} source={source} objects={objects} odor={odor.data ?? null} trail={trail} follow={follow} ambient={arena?.ambient ?? 0.6} />
        <div className="absolute left-3 top-3 flex flex-wrap gap-1.5" role="toolbar" aria-label="Fly controls">
          <button className="btn btn-primary" onClick={() => ctl("start")} disabled={!session || session.status !== "ready"}>▶ Start</button>
          <button className="btn" onClick={() => ctl("pause")} disabled={session?.status !== "running"}>❚❚ Pause</button>
          <button className="btn" onClick={() => ctl("resume")} disabled={session?.status !== "paused"}>▶ Resume</button>
          <button className="btn btn-danger" onClick={() => ctl("stop")} disabled={!session || ["stopped", "finished"].includes(session.status)}>■ Stop</button>
          <button className="btn" onClick={() => { setTrail([]); ctl("reset"); }} disabled={!session}>↺ Reset world</button>
          <button className="btn" onClick={() => setFollow((f) => !f)} aria-pressed={follow}>{follow ? "Following fly" : "Free camera"}</button>
          {session && <button className="btn" onClick={() => api.saveFly(session.id).then((r) => alert(`Saved recording ${r.recording_id}`), setErr)}>Save recording</button>}
        </div>
        <div className="absolute bottom-3 left-3 rounded-lg bg-ink-950/80 px-2 py-1 text-[11px] text-ink-300">
          {replay ? `Replaying ${replay.id}` : session ? `${session.label} · ${session.status}` : "Create a session to load the MuJoCo world"} · body pose from MuJoCo (FlyGym 2.1.1)
        </div>
      </div>

      <div className="space-y-3 overflow-y-auto">
        <Section title="State" right={session && <EvidenceBadge kind={session.evidence} />}>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Sim time" value={<span data-testid="fly-time">{fmt.num(frame?.t_s ?? session?.t_s ?? 0, 2)} s</span>} />
            <Stat label="Sim / wall" value={frame?.wall_s && frame.t_s ? `${(frame.t_s / frame.wall_s).toFixed(2)}×` : session?.sim_wall_ratio ? `${session.sim_wall_ratio.toFixed(2)}×` : "–"} hint="Simulated seconds per wall-clock second (measured). Not real time unless ≥1." />
            <Stat label="Position (mm)" value={frame?.pos ? `${frame.pos[0].toFixed(1)}, ${frame.pos[1].toFixed(1)}` : "–"} />
            <Stat label="Heading" value={frame?.heading_rad != null ? `${((frame.heading_rad * 180) / Math.PI).toFixed(0)}°` : "–"} />
          </div>
          <div className="mt-2 text-xs">
            <div className="mb-1 text-ink-400">Descending command [left, right]</div>
            {(frame?.ds ?? [0, 0]).map((v, i) => (
              <div key={i} className="mb-1 flex items-center gap-2">
                <span className="w-8 text-ink-400">{i ? "R" : "L"}</span>
                <div className="relative h-2 flex-1 rounded bg-ink-800"><div className="absolute top-0 h-2 rounded bg-accent" style={{ left: v >= 0 ? "50%" : `${50 + (v / 1.2) * 50}%`, width: `${(Math.abs(v) / 1.2) * 50}%` }} /></div>
                <span className="mono w-10 text-right">{v.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </Section>
        <Section title="Sensors (from MuJoCo state)">
          <dl className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-xs">
            {[["Odour + L", s.odor_attractive_left], ["Odour + R", s.odor_attractive_right], ["Odour − L", s.odor_aversive_left], ["Odour − R", s.odor_aversive_right], ["Luminance L", s.luminance_left], ["Luminance R", s.luminance_right], ["Contact L", s.contact_left], ["Contact R", s.contact_right], ["On food", s.on_food]].map(([k, v]) => (
              <div key={k as string} className="contents"><dt className="text-ink-400">{k}</dt><dd className="mono">{v == null ? "–" : (v as number).toFixed(3)}</dd></div>
            ))}
          </dl>
          {session?.vision_error ? (
            <p className="mt-1 text-[11px] text-amber-200" role="status">Vision unavailable on this machine (no OpenGL context): {session.vision_error}. Luminance inputs are 0.</p>
          ) : session && !session.vision && <p className="mt-1 text-[11px] text-ink-400">Vision off (enabled automatically in arenas with light sources).</p>}
        </Section>
        {session?.controller === "neural" && (
          <Section title="Neural interface">
            <div className="text-xs">
              <div className="mb-1 text-ink-400">Sensory input rates (Hz)</div>
              {Object.entries(frame?.input_hz ?? {}).map(([k, v]) => <div key={k} className="flex justify-between"><span className="truncate">{k}</span><span className="mono">{v.toFixed(0)}</span></div>)}
              <div className="mb-1 mt-2 text-ink-400">Descending readouts (smoothed Hz)</div>
              {Object.entries(frame?.readout_hz ?? {}).map(([k, v]) => <div key={k} className="flex justify-between"><span>{k}</span><span className="mono">{v.toFixed(1)}</span></div>)}
              {frame?.brain && <div className="mt-2 text-ink-400">Brain t = {fmt.ms(frame.brain.t_ms)}, {fmt.int(frame.brain.n_spikes)} spikes · session {session.brain_session_id} (view in Explorer → Simulated activity)</div>}
              {session.missing_groups.length > 0 && <p className="mt-1 text-amber-200">Unmapped groups: {session.missing_groups.join(", ")}</p>}
            </div>
          </Section>
        )}
        <Section title="Where does the behaviour come from?">
          <ul className="space-y-1 text-[11px] text-ink-300">
            <li><b className="text-ink-100">Physics & body:</b> MuJoCo + official NeuroMechFly model (FlyGym).</li>
            <li><b className="text-ink-100">Leg coordination:</b> FlyGym HybridTurningController (CPG + feedback rules) — an external algorithm, not the connectome.</li>
            {session?.controller === "neural" ? <>
              <li><b className="text-ink-100">Descending command:</b> smoothed spike rates of named descending neurons (FlyMind readout mapping, an assumption).</li>
              <li><b className="text-ink-100">Neural dynamics:</b> LIF simulation on {ds?.synthetic ? "a synthetic network" : "the FlyWire connectome"}.</li>
              <li><b className="text-ink-100">Sensory input:</b> sensor values → Poisson rates of mapped sensory neurons (FlyMind encoding).</li>
            </> : <li><b className="text-ink-100">Descending command:</b> set by you (scripted). No neural model involved.</li>}
          </ul>
        </Section>
        {traj && traj.rows.length > 1 && (
          <Section title="Behaviour">
            <div className="mb-2 grid grid-cols-2 gap-2">
              <Stat label="Distance (mm)" value={fmt.num(traj.metrics.distance_travelled_mm)} />
              <Stat label="Mean speed (mm/s)" value={fmt.num(traj.metrics.mean_speed_mm_s)} />
              <Stat label="Heading change" value={`${fmt.num(traj.metrics.heading_change_deg, 0)}°`} />
              <Stat label="Collisions" value={fmt.int(traj.metrics.collision_onsets)} />
            </div>
            <Plot height={180} testId="fly-trajectory" data={[{ type: "scatter", mode: "lines", x: traj.rows.map((r) => r.x_mm), y: traj.rows.map((r) => r.y_mm), line: { color: "#5eead4" }, name: "path" }]}
              layout={{ xaxis: { title: { text: "x (mm)" } }, yaxis: { title: { text: "y (mm)" }, scaleanchor: "x" }, showlegend: false, margin: { l: 40, r: 8, t: 8, b: 32 } }} />
            <Plot height={150} data={[
              { type: "scatter", mode: "lines", name: "L", x: traj.rows.map((r) => r.t_s), y: traj.rows.map((r) => r.ds_left), line: { width: 1 } },
              { type: "scatter", mode: "lines", name: "R", x: traj.rows.map((r) => r.t_s), y: traj.rows.map((r) => r.ds_right), line: { width: 1 } },
            ]} layout={{ xaxis: { title: { text: "t (s)" } }, yaxis: { title: { text: "descending" } }, margin: { l: 40, r: 8, t: 8, b: 32 } }} />
          </Section>
        )}
      </div>
    </div>
  );
}

function num(v: string) { const x = parseFloat(v); return Number.isFinite(x) ? x : 0; }

function ArenaEditor({ arena, onChange }: { arena: ArenaConfig; onChange: (a: ArenaConfig) => void }) {
  const set = (patch: Partial<ArenaConfig>) => onChange({ ...arena, ...patch, kind: arena.kind });
  return (
    <details className="text-xs" open={arena.kind === "experimental"}>
      <summary className="cursor-pointer text-ink-300">Edit objects & conditions</summary>
      <div className="mt-2 space-y-2">
        <Field label={`Ambient light ${arena.ambient.toFixed(2)}`}><input type="range" min={0} max={1} step={0.05} value={arena.ambient} onChange={(e) => set({ ambient: +e.target.value })} className="w-full" /></Field>
        {(["odor_sources", "obstacles", "lights", "food"] as const).map((key) => (
          <div key={key}>
            <div className="mb-1 flex items-center justify-between"><span className="text-ink-300">{{ odor_sources: "Odour sources", obstacles: "Obstacles", lights: "Light pillars", food: "Food patches" }[key]}</span>
              <button className="btn px-1.5 py-0 text-[11px]" onClick={() => {
                const defaults = { odor_sources: { x_mm: 15, y_mm: 0, peak: 1, scale_mm: 8, valence: "attractive", label: "" }, obstacles: { x_mm: 8, y_mm: 0, half_x_mm: 0.5, half_y_mm: 3, height_mm: 2, yaw_deg: 0, label: "" }, lights: { x_mm: 20, y_mm: 8, radius_mm: 2, height_mm: 12, intensity: 1, label: "" }, food: { x_mm: 15, y_mm: 0, radius_mm: 2, label: "" } }[key];
                set({ [key]: [...(arena[key] as unknown[]), defaults] } as Partial<ArenaConfig>);
              }}>+ add</button>
            </div>
            {(arena[key] as { x_mm: number; y_mm: number; valence?: string }[]).map((o, i) => (
              <div key={i} className="mb-1 flex items-center gap-1">
                <input aria-label={`${key} ${i} x`} className="input w-16 py-0.5" type="number" value={o.x_mm} onChange={(e) => { const l = [...(arena[key] as object[])] as { x_mm: number }[]; l[i] = { ...l[i], x_mm: num(e.target.value) }; set({ [key]: l } as Partial<ArenaConfig>); }} />
                <input aria-label={`${key} ${i} y`} className="input w-16 py-0.5" type="number" value={o.y_mm} onChange={(e) => { const l = [...(arena[key] as object[])] as { y_mm: number }[]; l[i] = { ...l[i], y_mm: num(e.target.value) }; set({ [key]: l } as Partial<ArenaConfig>); }} />
                {key === "odor_sources" && (
                  <select className="input py-0.5" value={o.valence} onChange={(e) => { const l = [...arena.odor_sources]; l[i] = { ...l[i], valence: e.target.value }; set({ odor_sources: l }); }}>
                    <option value="attractive">attractive</option><option value="aversive">aversive</option><option value="neutral">neutral</option>
                  </select>
                )}
                <button className="btn btn-danger px-1.5 py-0 text-[11px]" aria-label="Remove" onClick={() => set({ [key]: (arena[key] as object[]).filter((_, k) => k !== i) } as Partial<ArenaConfig>)}>✕</button>
              </div>
            ))}
          </div>
        ))}
        <p className="text-ink-400">Coordinates in mm; the fly starts at (0, 0) facing +x. Changes apply when you create a session.</p>
      </div>
    </details>
  );
}

function Recordings({ onReplay }: { onReplay: (r: { id: string; t: number[]; poses: Float32Array; n: number; rows: Record<string, number>[] }) => void }) {
  const recs = useAsync(() => api.recordings(), []);
  const [err, setErr] = useState<Error | null>(null);
  const list = useMemo(() => recs.data ?? [], [recs.data]);
  return (
    <Section title="Recorded sessions" right={<button className="btn px-1.5 py-0 text-[11px]" onClick={recs.reload}>↻</button>}>
      <ErrorBox error={err} />
      {list.length === 0 ? <p className="text-xs text-ink-400">Save a session to replay it here.</p> : (
        <ul className="max-h-56 space-y-1 overflow-y-auto text-xs">
          {list.map((r) => (
            <li key={r.recording_id} className="flex items-center gap-2 rounded border border-ink-700 px-2 py-1">
              <span className="flex-1 truncate" title={r.recording_id}>{r.label || r.arena} · {r.controller} · {fmt.num(r.metrics?.distance_travelled_mm)} mm</span>
              <button className="btn px-1.5 py-0 text-[11px]" onClick={() => api.recording(r.recording_id).then((d) => {
                if (!d.frames) throw new Error("recording has no pose frames");
                onReplay({ id: r.recording_id, t: d.frames.t_s, poses: new Float32Array(decodeB64(d.frames.poses_b64)), n: d.frames.shape[1], rows: d.trajectory.rows });
              }).catch(setErr)}>Replay</button>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
