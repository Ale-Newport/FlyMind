# Test results

Executed at commit `a4e2bcd` on macOS 27.0.1 (Apple M2 Max). Raw output is in
[`test-output/`](test-output/).

| Suite | Command | Result |
|---|---|---|
| Python unit + integration + full-data (FlyWire v783 and skeletons installed) | `uv run pytest -v --timeout=300` | **44 passed** (0 failed, 0 skipped; 24.7 s) |
| Frontend unit (Vitest, jsdom) | `cd apps/web && npx vitest run` | **9 passed** (2 files) |
| Browser end-to-end (Playwright, Chromium, isolated fixture-only backend) | `cd apps/web && npx playwright test` | **6 passed** (18.9 s) |
| Lint | `uv run ruff check src tests scripts` | All checks passed |
| Type check (TypeScript strict) | `cd apps/web && npx tsc -b` | no errors |

## What the suites cover

* **Data**:
  * int64 ID parsing and float64-corruption detection
  * CSR construction, duplicate rejection, sub-graphs, neighbourhoods, shortest paths
  * Codex-format import with neuropil aggregation and sign assignment
  * rejection of cross-release IDs
  * header-based detection
  * fixture validation
* **Dynamics**:
  * analytic threshold time and inter-spike interval
  * PSP waveform within 1e-9 mV
  * delay and sign
  * refractory freezing and the zero refractory period of stimulated neurons
  * discarding of input during refractoriness
  * seeded determinism and chunking independence
  * Numba vs NumPy equality
  * float32 vs float64 agreement
  * silencing modes and reversible lesions
  * inhibition
* **Brian2 equivalence**: identical spike trains under Poisson input, current input, silencing, scaling and sub-networks.
* **Experiments**:
  * every template builds
  * a persisted record replays identically
  * comparison
* **API**:
  * exact string IDs
  * path-traversal rejection
  * session lifecycle, WebSocket, export and save
  * input validation
  * background experiment job
* **Architecture**: layering.
* **Closed loop (MuJoCo)**:
  * baseline walking and the turning sign
  * obstacle contact
  * no walking without neural output
  * the full sensor → neuron → motor → body → sensor cycle
  * a perturbation changing the motor output
  * recording files with vision on
* **Full data**:
  * published v783 counts
  * sugar GRNs drive MN9 above 50 Hz with 200–800 neurons active
  * sugar GRN → MN9 pathway
  * skeleton LOD
* **Browser (e2e)**:
  * navigation and backend status
  * dataset provenance
  * explorer search, inspection and hand-off to the simulator
  * simulator create, stimulate, start, pause, scrub, stop and reset
  * virtual fly session streaming MuJoCo poses
  * experiment template run with results

## Bugs found by these tests (all fixed)

1. Refractory semantics differed from Brian2 (input during refractoriness must be discarded) — found by `test_brian2_equivalence.py` during development.
2. `resume()` after single-stepping did not start the worker thread (WebSocket test hung).
3. Stale session state in the UI from out-of-order responses disabled the Pause button (Playwright).
4. Lock starvation delayed controls by >1.5 s on the full brain (found while capturing screenshots; now 2–10 ms).
5. A descending neuron silenced by output block still counted in the motor readout (found in the embodied FlyWire experiment).
6. Unknown `/api/*` paths returned the web app instead of 404.
7. `make dev` exited immediately on macOS because `scripts/setup/dev.sh` used `wait -n`
   (unsupported by the bundled bash 3.2) — found by the fresh-clone check below.

## Fresh-clone check

`git clone --branch feature/flymind-v0.1 <repo> fresh && cd fresh && make setup && make test`
on the same machine (warm uv/npm caches): `make setup` 19 s; `make test` **31 passed,
13 deselected** (physics/Brian2/full-data markers); `uv run flymind data info` lists the
synthetic dataset with validation `passed`; `make dev API_PORT=8020 WEB_PORT=5190` serves
the API directly and through the web proxy. With the default ports occupied, `make dev`
stops with the documented port-conflict message.

## 0.2.0 verification (2026-11-19)

Local, macOS 27.0 (Apple M2 Max), commit `ba31e51`:

| Suite | Command | Result |
|---|---|---|
| Python, everything except full data (MuJoCo and Brian2 included) | `uv run pytest -m "not fulldata" --timeout=600` | **82 passed**, 4 deselected |
| Frontend unit + type check | `cd apps/web && npx tsc -b && npx vitest run` | **22 passed**, no type errors |
| Browser end-to-end (Playwright, Chromium) | `cd apps/web && npx playwright test` | **6 passed** |
| Documentation | `mkdocs build --strict` | built, no warnings |
| Dependency audit | `pip-audit --strict` on every locked package; `npm audit` | no known vulnerabilities |
| Secret scan | `gitleaks git .` over the full history | no leaks (one allow-listed false positive: a dataset key) |

GitHub Actions on `ba31e51`: CI (Python on Ubuntu and macOS, web type check/unit/e2e, docs
and static demo build), CodeQL (Python, TypeScript, Actions), Security (dependency audit,
TruffleHog history scan), OpenSSF Scorecard and the Pages deployment all succeeded. The
release workflow published v0.2.0 from the tag.

Fresh clone of `main` into an empty directory (warm uv/npm caches): `make setup` 10 s,
`make test` **67 passed**, 19 deselected; `flymind data info` lists the synthetic dataset with
validation `passed`.

### Bugs found in the 0.2.0 audit (all fixed, with regression tests in `tests/unit/test_api_hardening.py`)

1. The API answered any `Host` header, so a DNS-rebinding page could drive it.
2. WebSocket handshakes from any origin were accepted.
3. No request-body limit; unbounded list inputs and population bins could exhaust memory.
4. Per-condition parameter overrides bypassed `LIFParams` validation (`dt_ms=0` crashed a job; `dt_ms=1e-7` ran effectively forever).
5. Experiment jobs were unbounded and never pruned.
6. Invalid experiment, run and recording ids returned 500 instead of 404.
7. `max_points`/`max_rows` ≤ 0 divided by zero or reversed data.
8. Saving a fly recording while it ran could fail with mismatched row counts.
9. Fly sessions leaked or lost their brain sessions (failed creation, delete, eviction); session caps were racy.
10. Spike counting re-concatenated the whole history on every chunk.
11. Identifiers with a trailing newline passed validation.
12. Alt+digit shortcuts never fired on macOS; partner rows and the shortcuts dialog were not keyboard accessible (found by review; covered by the e2e suite's navigation checks).
