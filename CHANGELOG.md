# Changelog

All notable changes are documented here (format: Keep a Changelog; versioning: SemVer).

## [Unreleased]

### Fixed
- CI: use `macos-latest` (the `macos-14` runner is no longer supported); install Mesa EGL
  for headless MuJoCo rendering on Linux and set `MUJOCO_GL`/`PYOPENGL_PLATFORM` only there.
- `scripts/setup/e2e_api.sh`: portable `mktemp` template (GNU mktemp rejected `-t name`).
- Flaky simulator e2e test (stimulus ended before the live raster was checked).

### Changed
- CI failures are published as annotations (readable without signing in).
- Routine e2e runs write screenshots to `apps/web/test-results/`; set `E2E_SCREENSHOT_DIR`
  to refresh the committed evidence images.

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
