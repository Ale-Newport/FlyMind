// Shared API types. Root IDs are always strings: FlyWire IDs exceed 2^53 and
// would be silently rounded by JavaScript numbers.

export type Evidence =
  | "published"
  | "reproduced"
  | "simulation_output"
  | "hypothesis"
  | "demonstration";

export interface DatasetSummary {
  dataset_id: string;
  name: string;
  version: string;
  specimen: string;
  synthetic: boolean;
  n_neurons: number;
  n_edges: number;
  n_synapses: number;
  license: string;
  validation_status: string;
  imported_at: string;
  adapter: string;
  has_skeletons: boolean;
}

export interface Neuron {
  idx: number;
  root_id: string;
  name: string | null;
  side: string | null;
  flow: string | null;
  super_class: string | null;
  cell_class: string | null;
  cell_sub_class: string | null;
  cell_type: string | null;
  hemibrain_type: string | null;
  nt_type: string | null;
  nt_confidence: number | null;
  pos_x: number | null;
  pos_y: number | null;
  pos_z: number | null;
  primary_neuropil: string | null;
  input_synapses: number | null;
  output_synapses: number | null;
}

export interface NeuronDetail extends Neuron {
  connectivity: {
    downstream_partners: number;
    upstream_partners: number;
    output_synapses: number;
    input_synapses: number;
    sign_of_outputs: number | null;
  };
  dataset: { id: string; version: string; synthetic: boolean };
  source_url: string | null;
  has_skeleton: boolean;
}

export interface Partner {
  root_id: string;
  idx: number;
  cell_type: string | null;
  super_class: string | null;
  side: string | null;
  nt_type: string | null;
  primary_neuropil: string | null;
  syn_count: number;
  sign: number;
  fraction_of_total: number;
  model_weight_mV: number;
}

export interface PartnersResponse {
  root_id: string;
  direction: "upstream" | "downstream";
  min_syn: number;
  n_partners: number;
  total_synapses: number;
  partners: Partner[];
}

export interface Attribute {
  field: string;
  labels: string[];
  counts: number[];
  codes_b64: string;
}

export interface Group {
  name: string;
  description: string;
  source: string;
  evidence: Evidence | null;
  user_defined: boolean;
  n_neurons: number;
  root_ids: string[];
}

export interface Selector {
  root_ids?: string[];
  group?: string;
  cell_types?: string[];
  cell_type_regex?: string;
  super_class?: string[];
  side?: string[];
  nt_type?: string[];
  neuropils?: string[];
}

export interface StimulusSpec {
  kind: "poisson" | "pulse_train" | "current";
  selector: Selector;
  rate_hz?: number;
  frequency_hz?: number;
  amplitude_mV?: number;
  start_ms?: number;
  stop_ms?: number | null;
  repeats?: number;
  interval_ms?: number;
  label?: string;
}

export interface InterventionSpec {
  kind: "silence" | "synaptic_scaling";
  selector: Selector;
  post_selector?: Selector | null;
  mode?: "block_output" | "clamp";
  factor?: number;
  label?: string;
}

export interface SimSummary {
  id: string;
  label: string;
  dataset_id: string;
  synthetic: boolean;
  mode: string;
  n_neurons: number;
  n_edges: number;
  status: string;
  error: string | null;
  t_ms: number;
  max_duration_ms: number;
  dt_ms: number;
  seed: number;
  backend: string;
  speed: number | null;
  wall_running_s: number;
  sim_wall_ratio: number | null;
  n_spikes: number;
  probe_root_ids: string[];
  stimuli: (StimulusSpec & { id: string })[];
  interventions: (InterventionSpec & { id: string })[];
  evidence: Evidence;
}

export interface SimFrame {
  type: "frame" | "status" | "hello" | "error";
  t_ms?: number;
  status?: string;
  sim_wall_ratio?: number | null;
  wall_running_s?: number;
  n_spikes_total?: number;
  spike_t_ms?: number[];
  spike_idx?: number[];
  truncated?: boolean;
  probe_t_ms?: number[];
  probe_v?: number[][];
  session?: SimSummary;
  message?: string;
}

export interface Activity {
  t0_ms: number;
  t1_ms: number;
  idx: number[];
  rate_hz: number[];
  top: { idx: number; root_id: string; cell_type: string | null; rate_hz: number }[];
  regions: { label: string; spikes: number; neurons: number; mean_rate_hz: number }[];
  n_active: number;
}

export interface ArenaConfig {
  kind: string;
  name: string;
  description: string;
  odor_sources: { x_mm: number; y_mm: number; peak: number; scale_mm: number; valence: string; label: string }[];
  obstacles: { x_mm: number; y_mm: number; half_x_mm: number; half_y_mm: number; height_mm: number; yaw_deg: number; label: string }[];
  lights: { x_mm: number; y_mm: number; radius_mm: number; height_mm: number; intensity: number; label: string }[];
  food: { x_mm: number; y_mm: number; radius_mm: number; label: string }[];
  ambient: number;
  spawn_x_mm: number;
  spawn_y_mm: number;
  spawn_heading_deg: number;
}

export interface BridgeConfig {
  name: string;
  dataset_ids: string[];
  description: string;
  evidence: Evidence;
  sensory: { sensor: string; group: string; gain_hz: number; baseline: number; max_rate_hz: number; note: string }[];
  motor: { role: string; group: string; note: string }[];
  tau_ms: number;
  r_half_hz: number;
  tonic_forward: number;
  interval_ms: number;
}

export interface FlySummary {
  id: string;
  label: string;
  status: string;
  error: string | null;
  controller: "baseline" | "neural";
  arena: ArenaConfig;
  t_s: number;
  duration_s: number;
  wall_s: number;
  sim_wall_ratio: number | null;
  vision: boolean;
  vision_error?: string | null;
  brain_session_id: string | null;
  bridge: BridgeConfig | null;
  missing_groups: string[];
  baseline: { forward: number; turn: number };
  state: Record<string, number>;
  n_geoms: number;
  evidence: Evidence;
  scene?: SceneObject[];
}

export interface SceneObject {
  name: string;
  kind: string;
  type: "box" | "cylinder" | "sphere" | "other";
  size: number[];
  pos: number[];
  quat: number[];
  rgba: number[];
}

export interface FlyFrame {
  type: "frame" | "status" | "hello" | "error";
  t_s?: number;
  poses?: number[];
  pos?: number[];
  heading_rad?: number;
  ds?: [number, number];
  drive?: Record<string, number>;
  sensors?: Record<string, number>;
  readout_hz?: Record<string, number>;
  input_hz?: Record<string, number>;
  brain?: { t_ms: number; n_spikes: number };
  status?: string;
  error?: string | null;
  wall_s?: number;
  session?: FlySummary;
  scene?: SceneObject[];
}

export interface MeshMeta {
  geoms: { name: string; vertex_offset: number; n_vertices: number; face_offset: number; n_faces: number; rgba: number[]; group: number }[];
  units: string;
  source: string;
}

export interface TemplateInfo {
  key: string;
  title: string;
  dataset_id: string;
  available: boolean;
  spec: ExperimentSpec | null;
}

export interface ExperimentSpec {
  name: string;
  template: string;
  description: string;
  dataset_id: string;
  conditions: { name: string; stimuli: StimulusSpec[]; interventions: InterventionSpec[]; params: Record<string, unknown> }[];
  readouts: { name: string; selector: Selector }[];
  duration_ms: number;
  n_trials: number;
  seed: number;
  evidence: Evidence;
  assumptions: string[];
  embodiment: unknown | null;
  [key: string]: unknown;
}

export interface Job {
  id: string;
  kind: string;
  label: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  message: string;
  result: { experiment_id?: string } | null;
  error: string | null;
}

export interface ExperimentListItem {
  experiment_id: string;
  name: string;
  kind: string;
  template: string | null;
  created_at: string;
  evidence: Evidence | null;
  dataset_id: string | null;
  conditions: string[];
}
