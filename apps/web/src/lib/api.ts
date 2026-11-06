import type {
  Activity,
  ArenaConfig,
  Attribute,
  BridgeConfig,
  DatasetSummary,
  ExperimentListItem,
  ExperimentSpec,
  FlySummary,
  Group,
  InterventionSpec,
  Job,
  MeshMeta,
  NeuronDetail,
  Neuron,
  PartnersResponse,
  SimSummary,
  StimulusSpec,
  TemplateInfo,
} from "./types";
import { staticGet, staticGetBinary } from "./staticBackend";

export const STATIC_DEMO: boolean = typeof __STATIC_DEMO__ !== "undefined" && __STATIC_DEMO__;

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export class BackendRequiredError extends ApiError {
  constructor(path: string) {
    super(0, `This feature needs the local FlyMind backend (${path}). The public demo site only serves static, browser-side data.`);
  }
}

function messageOf(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (typeof d.message === "string") return d.message;
    if (Array.isArray(d)) return d.map((x) => (x as { msg?: string }).msg ?? JSON.stringify(x)).join("; ");
  }
  return fallback;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (STATIC_DEMO) {
    if (method !== "GET") throw new BackendRequiredError(path);
    return staticGet<T>(path);
  }
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail ?? j;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, messageOf(detail, `${res.status} ${res.statusText}`), detail);
  }
  return (await res.json()) as T;
}

export const get = <T>(path: string) => request<T>("GET", path);
export const post = <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {});
export const del = <T>(path: string) => request<T>("DELETE", path);

async function binary(path: string): Promise<ArrayBuffer> {
  if (STATIC_DEMO) return staticGetBinary(path);
  const res = await fetch(path);
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`);
  return res.arrayBuffer();
}

const q = (params: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const str = s.toString();
  return str ? `?${str}` : "";
};

export function wsUrl(path: string): string {
  // VITE_WS_ORIGIN (e.g. ws://127.0.0.1:8010) connects straight to the API instead of via the
  // dev-server proxy; by default WebSockets use the page's own host.
  const origin = import.meta.env.VITE_WS_ORIGIN as string | undefined;
  if (origin) return `${origin}${path}`;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
}

export const api = {
  health: () => get<{ status: string; version: string }>("/api/health"),
  system: () => get<Record<string, unknown>>("/api/system"),
  datasets: () => get<DatasetSummary[]>("/api/datasets"),
  dataset: (id: string) => get<Record<string, unknown>>(`/api/datasets/${id}`),
  validation: (id: string) => get<Record<string, unknown>>(`/api/datasets/${id}/validation`),
  sources: () => get<Record<string, unknown>>("/api/sources"),
  evidence: () => get<Record<string, string>>("/api/evidence"),
  params: () => get<{ defaults: Record<string, unknown>; info: Record<string, { units: string; description: string; source: string; status: string }> }>("/api/brain/params"),
  search: (ds: string, params: Record<string, string | number | undefined>) =>
    get<{ total: number; offset: number; results: Neuron[] }>(`/api/datasets/${ds}/neurons${q(params)}`),
  neuronAt: (ds: string, idx: number) => get<Neuron>(`/api/datasets/${ds}/index/${idx}`),
  neuron: (ds: string, rid: string) => get<NeuronDetail>(`/api/datasets/${ds}/neurons/${rid}`),
  partners: (ds: string, rid: string, direction: "upstream" | "downstream", minSyn: number, limit = 200) =>
    get<PartnersResponse>(`/api/datasets/${ds}/neurons/${rid}/partners${q({ direction, min_syn: minSyn, limit })}`),
  pathways: (ds: string, source: string, target: string, minSyn: number, maxDepth: number) =>
    get<{ found: boolean; path: Neuron[]; edges: { pre: string; post: string; syn_count: number; sign: number }[]; message?: string }>(
      `/api/datasets/${ds}/pathways${q({ source, target, min_syn: minSyn, max_depth: maxDepth })}`,
    ),
  subgraph: (ds: string, seeds: string, depth: number, direction: string, minSyn: number, maxNodes = 300) =>
    get<{ nodes: (Neuron & { hop: number })[]; edges: { pre_root_id: string; post_root_id: string; syn_count: number; sign: number }[]; truncated: boolean; note: string }>(
      `/api/datasets/${ds}/subgraph${q({ seeds, depth, direction, min_syn: minSyn, max_nodes: maxNodes })}`,
    ),
  subgraphCsvUrl: (ds: string, seeds: string, depth: number, direction: string, minSyn: number) =>
    `/api/datasets/${ds}/subgraph${q({ seeds, depth, direction, min_syn: minSyn, format: "csv" })}`,
  points: (ds: string) => binary(`/api/datasets/${ds}/points`).then((b) => new Float32Array(b)),
  attribute: (ds: string, field: string) => get<Attribute>(`/api/datasets/${ds}/attributes/${field}`),
  neuropils: (ds: string) => get<{ centroids: { neuropil: string; centroid_um: number[]; neurons: number }[]; note: string }>(`/api/datasets/${ds}/neuropils`),
  skeleton: (ds: string, rid: string, lod = 1) =>
    get<{ root_id: string; segments_b64: string; n_segments: number; soma_um: number[] | null; source: string; simplification: Record<string, unknown>; lod: number }>(
      `/api/datasets/${ds}/skeletons/${rid}${q({ lod })}`,
    ),
  groups: (ds: string) => get<Group[]>(`/api/datasets/${ds}/groups`),
  saveGroup: (ds: string, name: string, root_ids: string[], description: string) =>
    post<{ saved: string }>(`/api/datasets/${ds}/groups`, { name, root_ids, description }),

  // simulation
  createSim: (cfg: Record<string, unknown>) => post<SimSummary>("/api/sim/sessions", cfg),
  sims: () => get<SimSummary[]>("/api/sim/sessions"),
  sim: (id: string) => get<SimSummary>(`/api/sim/sessions/${id}`),
  deleteSim: (id: string) => del(`/api/sim/sessions/${id}`),
  control: (id: string, action: string, extra: Record<string, unknown> = {}) =>
    post<SimSummary>(`/api/sim/sessions/${id}/control`, { action, ...extra }),
  addStimulus: (id: string, spec: StimulusSpec & { relative?: boolean }) => post<SimSummary & { id: string }>(`/api/sim/sessions/${id}/stimuli`, spec),
  removeStimulus: (id: string, sid: string) => del<SimSummary>(`/api/sim/sessions/${id}/stimuli/${sid}`),
  addIntervention: (id: string, spec: InterventionSpec) => post<SimSummary & { id: string }>(`/api/sim/sessions/${id}/interventions`, spec),
  removeIntervention: (id: string, iid: string) => del<SimSummary>(`/api/sim/sessions/${id}/interventions/${iid}`),
  clearInterventions: (id: string) => post<SimSummary>(`/api/sim/sessions/${id}/interventions/clear`),
  setProbes: (id: string, root_ids: string[]) => post<SimSummary>(`/api/sim/sessions/${id}/probes`, { root_ids }),
  activity: (id: string, t0: number, t1?: number) => get<Activity>(`/api/sim/sessions/${id}/activity${q({ t0_ms: t0, t1_ms: t1 })}`),
  raster: (id: string, t0: number, t1?: number, neurons?: string, max = 30000) =>
    get<{ t_ms: number[]; idx: number[]; truncated: boolean }>(`/api/sim/sessions/${id}/raster${q({ t0_ms: t0, t1_ms: t1, neurons, max_spikes: max })}`),
  traces: (id: string) => get<{ root_ids: string[]; t_ms: number[]; v_mV: number[][] }>(`/api/sim/sessions/${id}/traces`),
  population: (id: string, groups: string[], binMs = 10) =>
    get<{ groups: Record<string, { n_neurons: number; t_ms: number[]; rate_hz: number[] }> }>(
      `/api/sim/sessions/${id}/population${q({ groups: groups.join(","), bin_ms: binMs })}`,
    ),
  exportUrl: (id: string, format: string) => `/api/sim/sessions/${id}/export?format=${format}`,
  saveSim: (id: string) => post<{ experiment_id: string }>(`/api/sim/sessions/${id}/save`),

  // virtual fly
  arenas: () => get<ArenaConfig[]>("/api/fly/arenas"),
  bridges: () => get<BridgeConfig[]>("/api/fly/bridges"),
  odorField: (arena: ArenaConfig) => post<{ x_mm: number[]; y_mm: number[]; attractive: number[][]; aversive: number[][] }>("/api/fly/odor-field", arena),
  meshMeta: () => get<MeshMeta>("/api/fly/meshes/meta"),
  meshData: () => binary("/api/fly/meshes/data"),
  createFly: (cfg: Record<string, unknown>) => post<FlySummary>("/api/fly/sessions", cfg),
  fly: (id: string) => get<FlySummary>(`/api/fly/sessions/${id}`),
  flyControl: (id: string, action: string) => post<FlySummary>(`/api/fly/sessions/${id}/control`, { action }),
  flyBaseline: (id: string, cmd: { forward: number; turn: number }) => post<FlySummary>(`/api/fly/sessions/${id}/baseline`, cmd),
  flyLocomotion: (id: string, mode: "walk" | "fly", altitude_mm?: number) => post<FlySummary>(`/api/fly/sessions/${id}/locomotion`, { mode, altitude_mm }),
  flyTrajectory: (id: string) => get<{ rows: Record<string, number>[]; metrics: Record<string, number> }>(`/api/fly/sessions/${id}/trajectory`),
  saveFly: (id: string) => post<{ recording_id: string }>(`/api/fly/sessions/${id}/save`),
  recordings: () => get<{ recording_id: string; created_at: string; controller: string; label: string; arena: string; metrics: Record<string, number>; evidence: string }[]>("/api/fly/recordings"),
  recording: (rid: string) =>
    get<{ record: Record<string, unknown>; trajectory: { rows: Record<string, number>[] }; frames: { t_s: number[]; shape: number[]; poses_b64: string } | null }>(`/api/fly/recordings/${rid}`),

  // experiments
  templates: (ds?: string) => get<TemplateInfo[]>(`/api/experiments/templates${q({ dataset_id: ds })}`),
  runExperiment: (spec: ExperimentSpec) => post<{ job_id: string; experiment_id: string }>("/api/experiments/run", { spec }),
  experiments: () => get<ExperimentListItem[]>("/api/experiments"),
  experiment: (id: string) => get<Record<string, unknown>>(`/api/experiments/${id}`),
  experimentFileUrl: (id: string, name: string) => `/api/experiments/${id}/files/${name}`,
  embodiedTrajectory: (id: string, run: string) => get<{ rows: Record<string, number>[] }>(`/api/experiments/${id}/runs/${run}/trajectory`),
  compare: (a: string, b: string, ca?: string, cb?: string) =>
    post<Record<string, unknown>>("/api/experiments/compare", { a, b, condition_a: ca, condition_b: cb }),
  job: (id: string) => get<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => post<Job>(`/api/jobs/${id}/cancel`),
};

export function decodeB64(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out.buffer;
}
