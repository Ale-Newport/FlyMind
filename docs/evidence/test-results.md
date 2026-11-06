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
