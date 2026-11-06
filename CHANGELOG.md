# Changelog

All notable changes are documented here (format: Keep a Changelog; versioning: SemVer).

## [0.1.0] — 2026-11-06

### Added
- Connectome data pipeline: open-source fetch bundles with pinned SHA-256 checksums,
  header-based detection of Codex/Zenodo/Shiu/annotation files, FlyWire FAFB v783 and
  v630 (Shiu) adapters, canonical Parquet + memory-mapped CSR storage, provenance
  manifests, integrity validation reports, synthetic fixture.
- LIF brain simulator (Shiu et al. 2024 model): Numba and NumPy engines with Brian2
  semantics, Brian2 reference engine, full-brain/region/circuit/demo modes, Poisson,
  pulse-train and current stimulation, two silencing modes, reversible synaptic scaling,
  interactive threaded sessions with WebSocket streaming.
- Brain Explorer 3D: 139,255-neuron point cloud, search, connectivity tables, pathway
  tracing, subgraph export, FlyWire skeletons with LOD, simulated-activity overlay.
- Virtual Fly: NeuroMechFly v2 body in MuJoCo via FlyGym 2.1.1, five arenas, odour,
  vision, contact and food sensing, baseline and neural controllers, documented
  neural–motor bridge, recording and replay.
- Experiments: ten templates, reproducible runner with full provenance, comparison,
  reproduction of the Shiu et al. sugar-GRN → MN9 result.
- FastAPI service, React/TypeScript web app, CLI, Makefile, tests (pytest, Vitest,
  Playwright), benchmarks, documentation, CI and GitHub Pages static demo.
