# Architecture overview

```
Official connectome releases (Zenodo / GitHub pinned commits / user-downloaded Codex files)
          │  flymind data fetch | import          (checksums, header detection)
          ▼
  connectome/  adapters ─► canonical tables + CSR + manifest + validation report
          │                       data/processed/<dataset_id>/
          ├──────────────────────────────┬───────────────────────────────┐
          ▼                              ▼                               ▼
  brain/  LIF engines             visualization/ geometry        connectome/ queries
  (numba · numpy · Brian2)        (points, skeleton LOD)         (partners, paths, subgraphs)
          │                              │                               │
          ▼                              │                               │
  embodiment/ bridge (encoder/decoder)   │                               │
          │                              │                               │
          ▼                              │                               │
  FlyGym / MuJoCo body + arenas          │                               │
          │                              │                               │
          └─► experiments/ (specs, runner, records, comparison) ◄───────┘
                                         │
                         api/ FastAPI (REST + WebSocket, jobs, sessions)
                                         │
                         apps/web  React + R3F + Plotly (Explorer · Simulator · Virtual Fly · Experiments)
```

## Layers

| Package | Responsibility | May import |
|---|---|---|
| `common` | paths (safe joins), logging (JSON lines), provenance, evidence categories, concurrency helpers | — |
| `connectome` | sources, header detection, adapters, canonical storage (Parquet + memory-mapped CSR), validation, selectors, sparse graph queries | common |
| `brain` | parameters, stimuli/interventions, kernels, engine, Brian2 reference, recording, interactive sessions | common, connectome |
| `visualization` | point clouds, category codes, skeleton index and LOD | common, connectome |
| `embodiment` | arenas, FlyGym body, sensors, neural–motor bridge, closed-loop sessions | common, connectome, brain |
| `experiments` | specs, templates, runner, persistence, comparison | all of the above |
| `api` | FastAPI service, sessions/jobs registry | all of the above |

`tests/unit/test_architecture.py` fails if a lower layer imports a higher one.

## Data pipeline

1. **Acquire**: `flymind data fetch <bundle>` downloads open files to `data/raw/<bundle>/`
   and verifies pinned SHA-256 checksums. Restricted sources (Codex) are imported from a
   user folder (`flymind data import`).
2. **Detect**: `connectome/detect.py` classifies files by magic bytes and header columns.
3. **Adapt**: an adapter for exactly one specimen/release builds `neurons.parquet`
   (dense `idx` sorted by int64 `root_id`), aggregated `edges.parquet`, CSR arrays,
   optional per-neuropil `connections.parquet` and `manifest.json`.
4. **Validate**: `connectome/validate.py` writes `validation_report.{json,md}` (ID dtype,
   uniqueness, float-corruption detection, CSR consistency, duplicates, signs, synapse
   totals, coordinates, expected counts).
5. **Serve**: `ConnectomeStore` memory-maps the CSR and exposes DuckDB views for
   analytical queries; the canonical tables are never modified by filters or views.

## Neural simulation engine

* State: `v`, `g`, `last_spike` (float64 by default), a ring buffer of spike indices of
  length `delay_steps + 1`.
* Per step: exact integration of non-refractory neurons, threshold, delivery of spikes
  emitted `delay` steps earlier through the CSR row of each spiking neuron (event-driven:
  cost ∝ spikes × out-degree), external input, reset.
* Numba kernel (`nogil`, cached), with a pure-NumPy twin used for testing.
* Interventions modify a derived weight vector and masks; the graph arrays are shared and
  read-only.
* Sessions run in worker threads in chunks (default 10 ms); controls take effect between
  chunks via a `YieldingLock` (control latency ≈ 2–10 ms on the full brain).

## Physics

FlyGym 2.1.1 builds the MJCF scene (NeuroMechFly body + `FlatGroundWorld` + FlyMind
obstacles/visuals); obstacles are registered as ground geoms so FlyGym creates explicit
contact pairs with legs, thorax, abdomen and head. MuJoCo steps at 0.1 ms. The browser
receives the world pose of each of the 69 body mesh geoms (7 floats each) at 30 Hz and the
compiled mesh vertices once (`/api/fly/meshes/*`, ~2 MB).

## Streaming

* `/ws/sim/{id}`: the worker pushes per-chunk frames into a bounded deque per subscriber
  (oldest dropped = backpressure); the socket merges and sends at a client-chosen interval
  (default 100 ms), truncating spikes to `max_spikes`; status messages only on change.
* `/ws/fly/{id}`: only the newest pose frame is sent each stream tick.
* Bulk data uses binary (`/points` float32) or base64 typed arrays (skeleton segments,
  category codes, replay frames). Root IDs are strings in all JSON.

## Frontend rendering

* Brain Explorer: one `THREE.Points` draw call for all neurons with a custom shader
  (per-point colour, alpha, size); colour/visibility changes update attribute buffers in
  place. Skeletons are `LineSegments` loaded per selected neuron at a requested LOD.
  Picking uses the points raycaster on click only.
* Virtual Fly: one mesh per body geom, poses written in `useFrame` from a ref (no React
  re-render per frame).
* Plotly charts are lazy-loaded; `Plotly.react` updates in place.

## Security

The API binds to `127.0.0.1` by default (a warning is printed otherwise), CORS is limited
to the local dev origins, all identifiers are validated against a strict pattern and
joined with `safe_join`, files are served only from a fixed artefact whitelist, request
models are bounded (durations, counts, rates), sessions and jobs are capped, and there is
no endpoint that executes user code or reads arbitrary paths.
