# Changelog

All notable changes are documented here (format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/)).

## [Unreleased]

## [0.2.1] — 2026-11-20

### Added
- `flymind data info --json` prints a machine-readable list of installed datasets (with the full
  manifest when a dataset is named) (#20).
- Automated accessibility checks: axe-core scans every page in the dark and light themes for
  WCAG 2.1 A/AA violations in the Playwright suite (#21).
- The end-to-end tests run in Firefox and WebKit as well as Chromium, locally
  (`PW_BROWSERS=chromium,firefox,webkit`) and in CI (#22).

### Changed
- TypeScript 7.0, FastAPI 0.163, uvicorn ≥ 0.54 and hatchling ≥ 1.33 (Dependabot #7, #25, #26, #27).

### Fixed
- The three figures in the evidence pages now have alt text describing what each plot shows, so a
  screen reader announces the figure rather than its file name (#18, thanks @tyza66).
- `flymind data info <dataset>` exits with an error for a dataset that is not installed instead of
  printing nothing.
- The Starlette test-client deprecation warning is gone: `httpx2` is a development dependency
  (#19). The runtime still uses `httpx` for downloads.
- **Simulation:** current stimuli are switched on and off on the integer step grid, like Poisson
  and pulse-train stimuli. Window edges just off the 0.1 ms grid (for example a relative stimulus
  at 3.3 + 1.0 ms) used to drop the drive for a whole segment or leave it on until the end of the
  chunk, so results depended on chunk size. The Brian2 reference uses the same rule.
- **Simulation:** stimuli with repeats but no interval, an open-ended window or overlapping
  repeats, and windows whose stop precedes their start, are rejected when submitted (422)
  instead of crashing the running session.
- **Data import:** Codex connections that reference a neuron outside the release are refused,
  even when their neuropil is unassigned; they were attached to a neighbouring neuron.
- **Analysis:** region activity in circuit and region mode counts only simulated neurons (mean
  rates were diluted by neurons that cannot spike). Full-brain results are unchanged.
- **Analysis:** population rates and experiment time courses use complete, half-open bins: a spike
  on a bin edge is no longer counted twice and a partial last bin no longer reads low.
- **Virtual Fly:** vision keeps refreshing in flight (luminance was frozen at take-off), and body
  time advances by exactly the bridge interval in flight (it drifted for intervals that are not
  whole milliseconds).
- **Live view:** merged stream frames take timing and spike totals from the newest simulation
  frame, not a trailing status message; `max_spikes=0` sends no spikes; probe traces restart
  when probes are added. After Reset, the Simulator clears the previous run's raster, time and
  counters. The Explorer activity colour scale uses the true maximum rate.
- **Web app:** when the browser cannot create a WebGL context (hardware acceleration off, a
  GPU-less VM), the 3D panels show "3D view unavailable" and the rest of the page keeps working;
  the whole app used to go blank. Found by the new Firefox CI run.

## [0.2.0] — 2026-11-19

### Added
- Flight for the Virtual Fly: a reduced-order model (wingbeat-averaged blade-element aerodynamics
  with Dickinson et al. 1999 coefficients, 6-DoF body, cascaded flight controller) with take-off,
  hover, forward flight, saccades and landing, hand-over to the FlyGym walking physics, wing
  flapping drawn on the real NeuroMechFly meshes, legs folding with height. Documented in
  `docs/scientific/flight.md`; labelled as a FlyMind model, not a FlyGym or connectome result.
- Autonomous fly-like behaviour policy (demonstration): walking, take-off, flight with saccades,
  odour tracking, landing on food, feeding, obstacle and aversive-odour avoidance.
- `/api/fly/sessions/{id}/locomotion` to switch walk/fly while a session runs.
- Security and maintenance automation: CodeQL (Python, TypeScript, Actions), dependency review,
  `pip-audit` and `npm audit`, TruffleHog history scans, OpenSSF Scorecard, a tag-driven release
  workflow, grouped Dependabot updates, a docs/static-demo build check on every pull request.
- Contributor onboarding: CODEOWNERS, issue forms, pull request template, expanded
  `CONTRIBUTING.md`, Contributor Covenant 2.1, `SECURITY.md` with private reporting,
  `.editorconfig`, `.gitattributes`, optional pre-commit hooks (gitleaks, ruff).
- README demo GIF recorded from the running app (`scripts/media/demo_gif.sh`) and a social preview
  card (`scripts/media/social_preview.html`).

### Changed
- Web app redesigned ("refined laboratory"): design tokens, dark and light themes with a
  system/light/dark toggle, themed charts and 3D scenes, restyled pages and components.
- CI failures are published as annotations (readable without signing in).
- Routine e2e runs write screenshots to `apps/web/test-results/`; set `E2E_SCREENSHOT_DIR`
  to refresh the committed evidence images.
- GitHub Actions are pinned to commit SHAs, check out without persisted credentials, and only the
  Pages deploy job holds `pages: write` / `id-token: write`.
- Dependencies updated (FastAPI 0.162.7, Typer 0.29, Vite 8.3.8, Tailwind 4.3.5, Playwright 1.65.1,
  and others). Pillow is raised to 13.0 over FlyGym's `<13` cap because every 12.x release has
  known vulnerabilities.

### Security
- The API now rejects requests whose `Host` header is not a loopback name (or listed in
  `FLYMIND_ALLOWED_HOSTS`), closing DNS-rebinding access to the unauthenticated local API.
- WebSocket handshakes from foreign origins are refused (CORS does not apply to WebSockets).
- Request bodies are capped at 4 MiB (`FLYMIND_MAX_BODY_BYTES`), list inputs have length limits,
  population-rate bins are bounded, and experiment condition overrides are fully validated, so a
  request can no longer allocate unbounded memory or schedule an effectively endless run.
- Experiment jobs are capped (8 queued or running; 429 beyond that) and finished jobs are pruned.
- Identifiers with a trailing newline are no longer accepted.

### Fixed
- Invalid experiment, run and recording identifiers return 404 instead of 500.
- `traces?max_points` and `trajectory?max_rows` reject values below 2 instead of dividing by zero
  or silently reversing the data.
- Saving a fly recording while it runs no longer fails with mismatched row counts.
- A failed neural fly-session creation no longer leaves an orphaned brain session; deleting or
  evicting a fly session removes its brain; the simulator never evicts the brain of a live fly;
  concurrent session creation can no longer exceed the session limits.
- Spike counting no longer re-concatenates the whole spike history on every simulation chunk
  (quadratic slow-down on long full-brain runs).
- A job cancelled before it started now records `finished_at`.
- Alt+1…7 page shortcuts work on macOS (Option+digit).
- Keyboard access: partner rows in the Brain Explorer can be selected with Enter/Space; the
  shortcuts dialog traps focus and returns it to its trigger.
- The Simulator and Virtual Fly show a message when the live stream disconnects instead of
  freezing silently; a failed "Save as experiment" is reported.
- CI: use `macos-latest` (the `macos-14` runner is no longer supported); install Mesa EGL
  for headless MuJoCo rendering on Linux and set `MUJOCO_GL`/`PYOPENGL_PLATFORM` only there.
- `scripts/setup/e2e_api.sh`: portable `mktemp` template (GNU mktemp rejected `-t name`).
- Flaky simulator e2e test (stimulus ended before the live raster was checked).
- Virtual Fly vision degrades explicitly when no OpenGL context exists (GPU-less macOS CI
  VMs: `CGLError: invalid pixel format`): vision is switched off, the reason is shown in
  the session and UI, and the session keeps running. The vision test skips with a reason
  where rendering is unavailable; recording/replay is tested separately.
- GitHub now detects the licence as MIT (the data-licence note moved to `THIRD_PARTY_NOTICES.md`).

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

[Unreleased]: https://github.com/Ale-Newport/FlyMind/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/Ale-Newport/FlyMind/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Ale-Newport/FlyMind/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Ale-Newport/FlyMind/releases/tag/v0.1.0
