import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { STATIC_DEMO, api, decodeB64, wsUrl } from "../lib/api";
import { useApp } from "../lib/store";
import type { ArenaConfig, BridgeConfig, FlightInfo, FlyFrame, FlySummary, LocomotionMode, SceneObject } from "../lib/types";
import { FlyScene, type PoseSource, buildFlyGeometries } from "../three/FlyScene";
import { Plot } from "../components/Plot";
import { useChartColors } from "../lib/colors";
import { Block, Empty, ErrorBox, EvidenceBadge, Field, Group, KV, Loading, Seg, Slider, fmt, useAsync, useDatasets, useInterval } from "../components/ui";
import { Icon } from "../components/Icon";

export default function VirtualFly() {
  const chart = useChartColors();
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
  const [controller, setController] = useState<"baseline" | "neural" | "autonomous">("baseline");
  const [locomotion, setLocomotion] = useState<LocomotionMode>("walk");
  const [altitude, setAltitude] = useState(8);
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
  const [saved, setSaved] = useState<string | null>(null);
  const [recsKey, setRecsKey] = useState(0);
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
        arena, controller, locomotion, altitude_mm: altitude, duration_s: duration, baseline: { forward, turn },
        bridge: bridge?.name ?? "synthetic_demo",
        brain: controller === "neural" ? { dataset_id: datasetId, network: { mode: ds?.synthetic ? "demo" : "full" } } : null,
        label: `${arena.name} · ${controller}${controller !== "autonomous" && locomotion === "fly" ? " · flight" : ""}`,
      });
      setSession(s); setObjects(s.scene ?? []);
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  const ctl = (action: string) => session && api.flyControl(session.id, action).then(setSession, setErr);
  const chooseLocomotion = (mode: LocomotionMode, alt = altitude) => {
    setLocomotion(mode);
    if (mode === "fly" && forward > 0.6) setForward(0.5); // a fly crosses the arena in a second at full speed
    if (session && session.controller !== "autonomous" && controller === session.controller && !["stopped", "finished", "error"].includes(session.status))
      api.flyLocomotion(session.id, mode, alt).then(setSession, setErr);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(t.tagName) || !session) return;
      if (e.code === "KeyF" && !e.metaKey && !e.ctrlKey && controller !== "autonomous") { e.preventDefault(); chooseLocomotion(locomotion === "fly" ? "walk" : "fly"); return; }
      if (e.code !== "Space") return;
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
    return <div className="mx-auto max-w-3xl px-8 py-12"><Empty title="The virtual fly needs the local backend.">MuJoCo physics (FlyGym) runs in Python; the browser only draws its state. Run <code>make dev</code> on your machine.</Empty></div>;
  }

  const s = frame?.sensors ?? {};
  const live = session && ["running", "paused"].includes(session.status);
  const toggle = session?.status === "running" ? { label: "Pause", icon: "pause" as const, run: () => ctl("pause"), disabled: false }
    : session?.status === "paused" ? { label: "Resume", icon: "play" as const, run: () => ctl("resume"), disabled: false }
    : { label: "Start", icon: "play" as const, run: () => ctl("start"), disabled: !session || session.status !== "ready" };
  const ground = (frame?.locomotion ?? session?.locomotion ?? "ground");
  return (
    <div className="tool min-w-[1080px]">
      <h1 className="sr-only">Virtual fly</h1>
      <aside aria-label="Fly setup" className="rail">
        <Group title="Environment">
          {!arenas.data ? <Loading /> : (
            <div className="space-y-3">
              <select aria-label="Arena" className="input" value={arena?.kind ?? ""} onChange={(e) => setArena(arenas.data!.find((a) => a.kind === e.target.value) ?? null)}>
                {arenas.data.map((a) => <option key={a.kind} value={a.kind}>{a.name}</option>)}
              </select>
              <p className="text-xs text-ink-3">{arena?.description}</p>
              {arena && <ArenaEditor arena={arena} onChange={setArena} />}
            </div>
          )}
        </Group>
        <Group title="Controller">
          <div className="space-y-4">
            <Seg kind="radio" fill label="Controller" value={controller} onChange={setController} options={[
              { value: "baseline", label: "Manual", title: "You set the descending command" },
              { value: "neural", label: "Neural", title: "Descending command read from the brain simulation" },
              { value: "autonomous", label: "Autonomous", title: "A scripted, fly-like forager" },
            ]} />
            {controller !== "autonomous" && (
              <div>
                <span className="label">Locomotion <span className="ml-1">(press <kbd>F</kbd> to switch)</span></span>
                <Seg kind="radio" fill label="Locomotion" value={locomotion} onChange={(m) => chooseLocomotion(m)} options={[
                  { value: "walk", label: <><Icon name="walk" size={14} />Walk</> },
                  { value: "fly", label: <><Icon name="fly" size={14} />Fly</> },
                ]} />
                {locomotion === "fly" && (
                  <div className="mt-3">
                    <Slider label="Flight height" unit="mm" value={altitude} min={3} max={30} step={1} onChange={(a) => { setAltitude(a); if (session && controller === session.controller) api.flyLocomotion(session.id, "fly", a).then(setSession, setErr); }} />
                  </div>
                )}
              </div>
            )}
            {controller === "autonomous" ? (
              <div className="space-y-2 text-xs text-ink-2">
                <p>A scripted, fly-like forager: walking bouts and pauses, take-off, straight flight segments with body saccades, odour tracking, landing on food, feeding, and avoidance of obstacles and aversive odour.</p>
                <p className="text-ink-3">A demonstration of behaviour, not a connectome result. Try the food arena. Walking runs the full FlyGym physics, so it is slower than flight.</p>
              </div>
            ) : controller === "baseline" ? (
              <>
                <p className="text-xs text-ink-3">{locomotion === "fly" ? "A scripted speed and turn rate go to the flight controller. The fly takes off, holds its height and lands by itself." : "A fixed descending command goes to FlyGym's walking controller. This checks the body mechanics independently of any neural model."}</p>
                <Slider label={locomotion === "fly" ? "Forward speed" : "Forward drive"} value={forward} min={-1.2} max={1.2} step={0.05} format={(v) => v.toFixed(2)} onChange={(v) => { setForward(v); if (session?.controller === "baseline") api.flyBaseline(session.id, { forward: v, turn }).then(setSession); }} />
                <Slider label="Turn, positive is left" value={turn} min={-1} max={1} step={0.05} format={(v) => v.toFixed(2)} onChange={(v) => { setTurn(v); if (session?.controller === "baseline") api.flyBaseline(session.id, { forward, turn: v }).then(setSession); }} />
              </>
            ) : (
              <div className="space-y-2 text-xs text-ink-2">
                <KV flush rows={[
                  ["Brain", ds?.synthetic ? "Synthetic demo network" : `${ds?.name ?? datasetId} v${ds?.version ?? ""}`],
                  ["Bridge", bridge ? <span key="b" className="inline-flex items-center gap-2">{bridge.name}</span> : <span key="b" style={{ color: "var(--danger)" }}>none defined</span>],
                ]} />
                {bridge && <div><EvidenceBadge kind={bridge.evidence} /></div>}
                <p className="text-ink-3">{bridge?.description}</p>
                {!bridge && <p style={{ color: "var(--danger)" }}>No neural–motor bridge is defined for this dataset.</p>}
                {!ds?.synthetic && <p style={{ color: "var(--warn)" }}>The full-brain closed loop runs well below real time, about 0.1 to 0.2 times on a laptop CPU.</p>}
              </div>
            )}
            <Field label="Duration" unit="s, simulated"><input type="number" className="input" min={0.5} max={120} step={0.5} value={duration} onChange={(e) => setDuration(+e.target.value)} /></Field>
            <button className="btn btn-primary btn-block" onClick={create} disabled={busy || !arena || (controller === "neural" && !bridge)}>{busy ? "Building MuJoCo model…" : "Create fly session"}</button>
          </div>
        </Group>
        <Recordings refreshKey={recsKey} onReplay={(r) => { setSession(null); setTrail(r.rows.map((x) => [x.x_mm, x.y_mm, x.z_mm])); setReplay(r); }} />
      </aside>

      <div className="stage theme-dark bg-paper">
        {meshes.loading && <div className="absolute left-1/2 top-1/2 z-10 -translate-x-1/2"><Loading label="Loading NeuroMechFly meshes" /></div>}
        <div className="absolute right-4 top-4 z-10 w-80"><ErrorBox error={meshes.error ?? err} /></div>
        <FlyScene parts={meshes.data ?? null} source={source} objects={objects} odor={odor.data ?? null} trail={trail} follow={follow} ambient={arena?.ambient ?? 0.6} />
        <div className="absolute left-4 top-4 flex flex-wrap items-center gap-2 border border-rule bg-paper/85 p-1" style={{ borderRadius: 3 }} role="toolbar" aria-label="Fly controls">
          <button className="btn btn-primary btn-sm" onClick={toggle.run} disabled={toggle.disabled}><Icon name={toggle.icon} size={14} />{toggle.label}</button>
          <button className="btn btn-danger btn-sm" onClick={() => ctl("stop")} disabled={!session || ["stopped", "finished"].includes(session.status)}><Icon name="stop" size={14} />Stop</button>
          <button className="btn btn-sm" onClick={() => { setTrail([]); ctl("reset"); }} disabled={!session}><Icon name="reset" size={14} />Reset world</button>
          <span aria-hidden className="mx-1 h-4 w-px bg-rule-strong" />
          <button className="btn btn-sm btn-quiet" onClick={() => setFollow((f) => !f)} aria-pressed={follow} data-tip={follow ? "The camera follows the fly" : "Free camera"}><Icon name={follow ? "follow" : "orbit"} size={14} />{follow ? "Following" : "Free camera"}</button>
          {session && <button className="btn btn-sm btn-quiet" onClick={() => api.saveFly(session.id).then((r) => { setSaved(`Saved recording ${r.recording_id}`); setRecsKey((k) => k + 1); }, setErr)}><Icon name="save" size={14} />Save recording</button>}
        </div>
        {saved && <div role="status" className="overlay absolute left-4 top-[60px] mono">{saved}</div>}
        <div className="overlay absolute bottom-3 left-4 max-w-[calc(100%-2rem)]">
          {replay ? `Replaying ${replay.id}` : session ? `${session.label}, ${session.status}` : "Create a session to load the MuJoCo world"}
          {" · "}
          {frame?.flight ? `flight model, wings drawn ${(frame.flight.wingbeat_hz / frame.flight.wing_display_hz).toFixed(0)} times slower than real` : "body pose from MuJoCo (FlyGym 2.1.1)"}
        </div>
      </div>

      <aside aria-label="Fly state" className="inspector">
        <Block title="State" right={session && <EvidenceBadge kind={session.evidence} />}>
          {session && (
            <div className="mb-4 flex items-baseline justify-between gap-3" data-testid="fly-behavior">
              <span className="t-head !text-xl">{frame?.behavior ?? session.behavior ?? "–"}</span>
              <span className="text-xs text-ink-3">{ground}</span>
            </div>
          )}
          <KV rows={[
            ["Simulated time", <span key="t" data-testid="fly-time">{fmt.num(frame?.t_s ?? session?.t_s ?? 0, 2)}</span>, "s"],
            [<span key="r" title="Simulated seconds per wall-clock second, measured. Not real time unless at least 1.">Simulated per wall second</span>, frame?.wall_s && frame.t_s ? (frame.t_s / frame.wall_s).toFixed(2) : session?.sim_wall_ratio ? session.sim_wall_ratio.toFixed(2) : "–", "×"],
            ["Position", frame?.pos ? `${fmt.num(frame.pos[0])}, ${fmt.num(frame.pos[1])}` : "–", "mm"],
            ["Heading", frame?.heading_rad != null ? fmt.num((frame.heading_rad * 180) / Math.PI, 0) : "–", "°"],
          ]} />
          <div className="mt-4">
            <div className="label">Descending command, left and right</div>
            {(frame?.ds ?? [0, 0]).map((v, i) => (
              <div key={i} className="mb-1.5 flex items-center gap-2 text-xs">
                <span className="w-3 text-ink-3">{i ? "R" : "L"}</span>
                <div className="relative h-[6px] flex-1 bg-rule">
                  <div className="absolute inset-y-0 left-1/2 w-px bg-ink-4" />
                  <div className="absolute top-0 h-[6px] bg-accent" style={{ left: v >= 0 ? "50%" : `${50 + (v / 1.2) * 50}%`, width: `${(Math.abs(v) / 1.2) * 50}%` }} />
                </div>
                <span className="mono w-10 text-right">{v.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </Block>
        {frame?.flight && (
          <Block title="Flight" right={<span className="mono text-xs text-ink-3">{frame.flight.wingbeat_hz.toFixed(0)} Hz wingbeat</span>}>
            <FlightPanel f={frame.flight} />
          </Block>
        )}
        <Group title="Sensors" meta="from the MuJoCo state">
          <KV rows={[["Odour, attractive, left", s.odor_attractive_left], ["Odour, attractive, right", s.odor_attractive_right], ["Odour, aversive, left", s.odor_aversive_left], ["Odour, aversive, right", s.odor_aversive_right], ["Luminance, left", s.luminance_left], ["Luminance, right", s.luminance_right], ["Contact, left", s.contact_left], ["Contact, right", s.contact_right], ["On food", s.on_food], ["Airborne", s.airborne]].map(([k, v]) => [k, v == null ? "–" : (v as number).toFixed(3)] as const)} />
          {session?.vision_error ? (
            <p className="mt-3 text-xs" style={{ color: "var(--warn)" }} role="status">Vision is unavailable on this machine (no OpenGL context): {session.vision_error}. Luminance inputs are 0.</p>
          ) : session && !session.vision && <p className="mt-3 text-xs text-ink-3">Vision is off. It turns on automatically in arenas with light sources.</p>}
        </Group>
        {session?.controller === "neural" && (
          <Group title="Neural interface">
            <div className="text-xs">
              <div className="label">Sensory input rates</div>
              <KV rows={Object.entries(frame?.input_hz ?? {}).map(([k, v]) => [k, v.toFixed(0), "Hz"] as const)} />
              <div className="label mt-4">Descending readouts, smoothed</div>
              <KV rows={Object.entries(frame?.readout_hz ?? {}).map(([k, v]) => [k, v.toFixed(1), "Hz"] as const)} />
              {frame?.brain && <p className="mt-3 text-ink-3">Brain t = {fmt.ms(frame.brain.t_ms)}, {fmt.int(frame.brain.n_spikes)} spikes. Session {session.brain_session_id}; view it in the explorer under Simulated activity.</p>}
              {session.missing_groups.length > 0 && <p className="mt-2" style={{ color: "var(--warn)" }}>Unmapped groups: {session.missing_groups.join(", ")}</p>}
            </div>
          </Group>
        )}
        {traj && traj.rows.length > 1 && (
          <Group title="Behaviour" meta={live ? "live" : undefined}>
            <KV rows={[
              ["Distance", fmt.num(traj.metrics.distance_travelled_mm), "mm"],
              ["Mean speed", fmt.num(traj.metrics.mean_speed_mm_s), "mm/s"],
              ["Heading change", fmt.num(traj.metrics.heading_change_deg, 0), "°"],
              ["Collisions", fmt.int(traj.metrics.collision_onsets)],
              traj.metrics.n_takeoffs > 0 && ["Airborne", fmt.num(traj.metrics.airborne_time_s), "s"],
              traj.metrics.n_takeoffs > 0 && ["Max height", fmt.num(traj.metrics.max_altitude_mm), "mm"],
              traj.metrics.time_feeding_s > 0 && ["Feeding", fmt.num(traj.metrics.time_feeding_s), "s"],
            ]} />
            <div className="-mx-1 mt-4 space-y-1">
              <Plot height={190} testId="fly-trajectory" data={[{ type: "scatter", mode: "lines", x: traj.rows.map((r) => r.x_mm), y: traj.rows.map((r) => r.y_mm), line: { color: chart.accent, width: 1.5 }, name: "path" }]}
                layout={{ xaxis: { title: { text: "x (mm)" } }, yaxis: { title: { text: "y (mm)" }, scaleanchor: "x" }, showlegend: false, margin: { l: 40, r: 8, t: 8, b: 32 } }} />
              {traj.rows.some((r) => r.airborne > 0) && (
                <Plot height={140} testId="fly-altitude" data={[{ type: "scatter", mode: "lines", x: traj.rows.map((r) => r.t_s), y: traj.rows.map((r) => Math.max(0, r.z_mm - 1.16)), line: { color: chart.accent, width: 1.5 }, name: "height" }]}
                  layout={{ xaxis: { title: { text: "t (s)" } }, yaxis: { title: { text: "height (mm)" } }, showlegend: false, margin: { l: 40, r: 8, t: 8, b: 32 } }} />
              )}
              <Plot height={150} endLabels data={[
                { type: "scatter", mode: "lines", name: "L", x: traj.rows.map((r) => r.t_s), y: traj.rows.map((r) => r.ds_left), line: { width: 1.2, color: chart.accent } },
                { type: "scatter", mode: "lines", name: "R", x: traj.rows.map((r) => r.t_s), y: traj.rows.map((r) => r.ds_right), line: { width: 1.2, color: chart.accent2 } },
              ]} layout={{ xaxis: { title: { text: "t (s)" } }, yaxis: { title: { text: "descending" } }, margin: { l: 40, r: 24, t: 8, b: 32 } }} />
            </div>
          </Group>
        )}
        <Group title="Where the behaviour comes from" defaultOpen={false}>
          <ul className="space-y-2.5 text-xs leading-5 text-ink-2">
            <li><b className="font-medium text-ink">Physics and body.</b> MuJoCo with the official NeuroMechFly model (FlyGym).</li>
            <li><b className="font-medium text-ink">Leg coordination.</b> FlyGym's HybridTurningController (CPG plus feedback rules), an external algorithm and not the connectome.</li>
            <li><b className="font-medium text-ink">Flight.</b> A FlyMind model, since FlyGym has none: wingbeat-averaged blade-element aerodynamics with the Dickinson 1999 coefficients, a 6-DoF body and a feedback flight controller. Rotational circulation, added mass, wake capture and wind are not modelled.</li>
            {session?.controller === "neural" ? <>
              <li><b className="font-medium text-ink">Descending command.</b> Smoothed spike rates of named descending neurons, through FlyMind's readout mapping (an assumption).</li>
              <li><b className="font-medium text-ink">Neural dynamics.</b> A leaky integrate-and-fire simulation of {ds?.synthetic ? "a synthetic network" : "the FlyWire connectome"}.</li>
              <li><b className="font-medium text-ink">Sensory input.</b> Sensor values become Poisson rates of mapped sensory neurons (FlyMind's encoding).</li>
            </> : session?.controller === "autonomous" ? <li><b className="font-medium text-ink">Behaviour.</b> A scripted, fly-like policy that reads the fly's own sensors. A demonstration, not the connectome.</li> : <li><b className="font-medium text-ink">Descending command.</b> Set by you, scripted. No neural model is involved.</li>}
          </ul>
        </Group>
      </aside>
    </div>
  );
}

function num(v: string) { const x = parseFloat(v); return Number.isFinite(x) ? x : 0; }

function ArenaEditor({ arena, onChange }: { arena: ArenaConfig; onChange: (a: ArenaConfig) => void }) {
  const set = (patch: Partial<ArenaConfig>) => onChange({ ...arena, ...patch, kind: arena.kind });
  return (
    <details className="disclose text-xs" open={arena.kind === "experimental"}>
      <summary>Edit objects and conditions</summary>
      <div className="mt-3 space-y-4">
        <Slider label="Ambient light" value={arena.ambient} min={0} max={1} step={0.05} format={(v) => v.toFixed(2)} onChange={(v) => set({ ambient: v })} />
        {(["odor_sources", "obstacles", "lights", "food"] as const).map((key) => (
          <div key={key}>
            <div className="mb-1 flex items-center justify-between"><span className="text-ink-2">{{ odor_sources: "Odour sources", obstacles: "Obstacles", lights: "Light pillars", food: "Food patches" }[key]}</span>
              <button className="btn btn-sm btn-quiet" onClick={() => {
                const defaults = { odor_sources: { x_mm: 15, y_mm: 0, peak: 1, scale_mm: 8, valence: "attractive", label: "" }, obstacles: { x_mm: 8, y_mm: 0, half_x_mm: 0.5, half_y_mm: 3, height_mm: 2, yaw_deg: 0, label: "" }, lights: { x_mm: 20, y_mm: 8, radius_mm: 2, height_mm: 12, intensity: 1, label: "" }, food: { x_mm: 15, y_mm: 0, radius_mm: 2, label: "" } }[key];
                set({ [key]: [...(arena[key] as unknown[]), defaults] } as Partial<ArenaConfig>);
              }}><Icon name="plus" size={12} />Add</button>
            </div>
            {(arena[key] as { x_mm: number; y_mm: number; valence?: string }[]).map((o, i) => (
              <div key={i} className="mb-1 flex items-center gap-1.5">
                <input aria-label={`${key} ${i} x`} className="input input-sm !w-14" type="number" value={o.x_mm} onChange={(e) => { const l = [...(arena[key] as object[])] as { x_mm: number }[]; l[i] = { ...l[i], x_mm: num(e.target.value) }; set({ [key]: l } as Partial<ArenaConfig>); }} />
                <input aria-label={`${key} ${i} y`} className="input input-sm !w-14" type="number" value={o.y_mm} onChange={(e) => { const l = [...(arena[key] as object[])] as { y_mm: number }[]; l[i] = { ...l[i], y_mm: num(e.target.value) }; set({ [key]: l } as Partial<ArenaConfig>); }} />
                {key === "odor_sources" && (
                  <select aria-label={`Odour source ${i} valence`} className="input input-sm" value={o.valence} onChange={(e) => { const l = [...arena.odor_sources]; l[i] = { ...l[i], valence: e.target.value }; set({ odor_sources: l }); }}>
                    <option value="attractive">attractive</option><option value="aversive">aversive</option><option value="neutral">neutral</option>
                  </select>
                )}
                <button className="btn btn-icon btn-sm btn-quiet ml-auto" aria-label="Remove" onClick={() => set({ [key]: (arena[key] as object[]).filter((_, k) => k !== i) } as Partial<ArenaConfig>)}><Icon name="close" size={12} /></button>
              </div>
            ))}
          </div>
        ))}
        <p className="text-ink-3">Coordinates are in mm. The fly starts at (0, 0) facing +x. Changes apply when you create a session.</p>
      </div>
    </details>
  );
}

function Recordings({ onReplay, refreshKey }: { onReplay: (r: { id: string; t: number[]; poses: Float32Array; n: number; rows: Record<string, number>[] }) => void; refreshKey: number }) {
  const recs = useAsync(() => api.recordings(), [refreshKey]);
  const [err, setErr] = useState<Error | null>(null);
  const list = useMemo(() => recs.data ?? [], [recs.data]);
  return (
    <Group title="Recorded sessions" defaultOpen={list.length > 0} meta={list.length ? String(list.length) : undefined}>
      <ErrorBox error={err} />
      {list.length === 0 ? <p className="text-xs text-ink-3">Save a session to replay it here.</p> : (
        <ul className="-mt-1 max-h-56 overflow-y-auto text-xs">
          {list.map((r) => (
            <li key={r.recording_id} className="flex items-center gap-2 border-t border-rule py-1.5">
              <span className="flex-1 truncate" title={r.recording_id}>{r.label || r.arena}<span className="block text-[11px] text-ink-3">{r.controller}, <span className="mono">{fmt.num(r.metrics?.distance_travelled_mm)}</span> mm</span></span>
              <button className="btn btn-sm" onClick={() => api.recording(r.recording_id).then((d) => {
                if (!d.frames) throw new Error("recording has no pose frames");
                onReplay({ id: r.recording_id, t: d.frames.t_s, poses: new Float32Array(decodeB64(d.frames.poses_b64)), n: d.frames.shape[1], rows: d.trajectory.rows });
              }).catch(setErr)}><Icon name="play" size={12} />Replay</button>
            </li>
          ))}
        </ul>
      )}
      <button className="btn btn-sm btn-quiet mt-2" onClick={recs.reload}><Icon name="refresh" size={12} />Refresh</button>
    </Group>
  );
}

/** Artificial horizon: pitch (nose-up positive) shifts the horizon down, roll tilts it. */
function Attitude({ pitch, roll }: { pitch: number; roll: number }) {
  return (
    <svg viewBox="-50 -50 100 100" width={96} height={96} role="img" aria-label={`Attitude: pitch ${pitch.toFixed(0)} degrees, roll ${roll.toFixed(0)} degrees`} className="shrink-0">
      <defs><clipPath id="fly-att"><circle r="46" /></clipPath></defs>
      <g clipPath="url(#fly-att)">
        <g transform={`rotate(${-roll}) translate(0 ${Math.max(-40, Math.min(40, pitch)) * 1.1})`}>
          <rect x="-120" y="-120" width="240" height="120" style={{ fill: "color-mix(in oklab, var(--accent) 16%, transparent)" }} />
          <rect x="-120" y="0" width="240" height="120" style={{ fill: "var(--paper-3)" }} />
          <line x1="-120" x2="120" y1="0" y2="0" style={{ stroke: "var(--accent)" }} strokeWidth="1" />
          {[-20, -10, 10, 20].map((p) => <line key={p} x1={-7} x2={7} y1={-p * 1.1} y2={-p * 1.1} style={{ stroke: "var(--ink-3)" }} strokeWidth="0.8" />)}
        </g>
      </g>
      <circle r="46" fill="none" style={{ stroke: "var(--ink-4)" }} strokeWidth="1" />
      <path d="M -20 0 H -7 M 7 0 H 20 M 0 -2.5 V 2.5" style={{ stroke: "var(--ink)" }} strokeWidth="1.8" fill="none" />
    </svg>
  );
}

function FlightPanel({ f }: { f: FlightInfo }) {
  const bar = (v: number) => `${Math.max(0, Math.min(100, (v / 180) * 100))}%`;
  return (
    <div className="space-y-4 text-xs">
      <div className="flex items-center gap-4">
        <Attitude pitch={f.pitch_deg} roll={f.roll_deg} />
        <KV className="flex-1" flush rows={[
          ["Height", fmt.num(f.altitude_mm, 1), "mm"], ["Speed", fmt.num(f.speed_mm_s, 0), "mm/s"], ["Climb", fmt.num(f.vz_mm_s, 0), "mm/s"],
          ["Pitch", fmt.num(f.pitch_deg, 0), "°"], ["Roll", fmt.num(f.roll_deg, 0), "°"], ["Yaw rate", fmt.num(f.yaw_rate_deg_s, 0), "°/s"],
        ]} />
      </div>
      <div>
        <div className="label">Stroke amplitude, peak to peak</div>
        {(["L", "R"] as const).map((side, i) => (
          <div key={side} className="mb-1.5 flex items-center gap-2">
            <span className="w-3 text-ink-3">{side}</span>
            <div className="relative h-[6px] flex-1 bg-rule"><div className="absolute left-0 top-0 h-[6px] bg-accent" style={{ width: bar(f.wing_amp_deg[i]) }} /></div>
            <span className="mono w-10 text-right">{f.wing_amp_deg[i].toFixed(0)}<span className="unit" style={{ marginLeft: 0 }}>°</span></span>
          </div>
        ))}
        <KV flush className="mt-2" rows={[["Thrust to weight", f.thrust_over_weight.toFixed(2)]]} />
      </div>
    </div>
  );
}
