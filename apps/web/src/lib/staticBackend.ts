// Read-only, browser-side backend for the GitHub Pages demo. It serves a static
// snapshot of the SYNTHETIC fixture (exported by scripts/data/export_static_demo.py).
// Anything that needs the Python simulation engine or MuJoCo raises
// BackendRequiredError in api.ts; nothing here pretends to simulate.
import type { Neuron, Partner } from "./types";

const base = () => `${import.meta.env.BASE_URL}demo/`;
const cache = new Map<string, Promise<unknown>>();

function load<T>(name: string): Promise<T> {
  if (!cache.has(name)) {
    cache.set(
      name,
      fetch(base() + name).then((r) => {
        if (!r.ok) throw new Error(`static demo file ${name} missing`);
        return r.json();
      }),
    );
  }
  return cache.get(name) as Promise<T>;
}

interface Edges { pre: number[]; post: number[]; syn: number[]; sign: number[] }

export async function staticGetBinary(path: string): Promise<ArrayBuffer> {
  if (/\/points$/.test(path)) {
    const r = await fetch(base() + "points.bin");
    return r.arrayBuffer();
  }
  throw new Error(`static demo has no binary resource for ${path}`);
}

export async function staticGet<T>(path: string): Promise<T> {
  const url = new URL(path, "http://x");
  const p = url.pathname;
  const params = url.searchParams;
  if (p === "/api/health") return { status: "static-demo", version: "static" } as T;
  if (p === "/api/datasets") return load<T>("datasets.json");
  if (p === "/api/sources") return load<T>("sources.json");
  if (p === "/api/evidence") return load<T>("evidence.json");
  if (p === "/api/brain/params") return load<T>("params.json");
  if (p === "/api/system") return { static_demo: true, capabilities: {}, datasets: [] } as T;
  let m = p.match(/^\/api\/datasets\/([^/]+)$/);
  if (m) return load<T>("manifest.json");
  if (p.endsWith("/validation")) return load<T>("validation.json");
  m = p.match(/\/attributes\/([a-z_]+)$/);
  if (m) return load<T>(`attr_${m[1]}.json`);
  if (p.endsWith("/neuropils")) return load<T>("neuropils.json");
  if (p.endsWith("/groups")) return load<T>("groups.json");
  const neurons = await load<Neuron[]>("neurons.json");
  if (p.endsWith("/neurons")) {
    const qs = (params.get("q") ?? "").toLowerCase();
    let hits = neurons.filter((n) =>
      !qs ? true : n.root_id.startsWith(qs) || (n.cell_type ?? "").toLowerCase().includes(qs) || (n.name ?? "").toLowerCase().includes(qs),
    );
    for (const key of ["super_class", "cell_type", "side", "nt_type"] as const) {
      const v = params.get(key);
      if (v) hits = hits.filter((n) => n[key] === v);
    }
    const limit = Number(params.get("limit") ?? 50);
    const offset = Number(params.get("offset") ?? 0);
    return { total: hits.length, offset, results: hits.slice(offset, offset + limit) } as T;
  }
  m = p.match(/\/index\/(\d+)$/);
  if (m) return neurons[Number(m[1])] as T;
  const edges = await load<Edges>("edges.json");
  m = p.match(/\/neurons\/(\d+)\/partners$/);
  if (m) {
    const n = neurons.find((x) => x.root_id === m![1]);
    if (!n) throw new Error("neuron not found");
    const down = params.get("direction") !== "upstream";
    const minSyn = Number(params.get("min_syn") ?? 1);
    const rows: Partner[] = [];
    let total = 0;
    for (let k = 0; k < edges.pre.length; k++) {
      const self = down ? edges.pre[k] : edges.post[k];
      if (self !== n.idx || edges.syn[k] < minSyn) continue;
      const other = neurons[down ? edges.post[k] : edges.pre[k]];
      total += edges.syn[k];
      rows.push({
        root_id: other.root_id, idx: other.idx, cell_type: other.cell_type, super_class: other.super_class,
        side: other.side, nt_type: other.nt_type, primary_neuropil: other.primary_neuropil,
        syn_count: edges.syn[k], sign: edges.sign[k], fraction_of_total: 0, model_weight_mV: edges.sign[k] * edges.syn[k] * 0.275,
      });
    }
    rows.forEach((r) => (r.fraction_of_total = total ? r.syn_count / total : 0));
    rows.sort((a, b) => b.syn_count - a.syn_count);
    return { root_id: n.root_id, direction: down ? "downstream" : "upstream", min_syn: minSyn, n_partners: rows.length, total_synapses: total, partners: rows } as T;
  }
  m = p.match(/\/neurons\/(\d+)$/);
  if (m) {
    const n = neurons.find((x) => x.root_id === m![1]);
    if (!n) throw new Error("neuron not found");
    let outP = 0, inP = 0, outS = 0, inS = 0;
    for (let k = 0; k < edges.pre.length; k++) {
      if (edges.pre[k] === n.idx) { outP++; outS += edges.syn[k]; }
      if (edges.post[k] === n.idx) { inP++; inS += edges.syn[k]; }
    }
    return {
      ...n,
      connectivity: { downstream_partners: outP, upstream_partners: inP, output_synapses: outS, input_synapses: inS, sign_of_outputs: null },
      dataset: { id: "synthetic_demo_v1", version: "1", synthetic: true },
      source_url: null,
      has_skeleton: false,
    } as T;
  }
  throw new Error(`static demo: ${p} requires the local backend`);
}
