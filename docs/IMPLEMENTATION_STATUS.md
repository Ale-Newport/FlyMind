# Implementation status

Last updated 2026-11-06 (code at commit `a4e2bcd`, branch `feature/flymind-v0.1`).
Environment: macOS 27.0.1, Apple M2 Max (12 cores, 64 GB), Python 3.13.16 (uv-managed),
Node 26, Chromium (Playwright 1.65).

## Phase 1: Research and architecture: complete

* **Done**
  * Inspected 10 repositories (commit SHAs recorded) and wrote the comparison matrix in `docs/research/reference-repositories.md`.
  * Verified the FlyGym 2.1.1 API by running it.
  * Audited licences.
  * Wrote seven ADRs and the architecture overview.
  * Established a layered package with an enforced import rule.
* **Tests:** `tests/unit/test_architecture.py`
* **Remaining:** none.

## Phase 2: Connectome data pipeline: complete

* **Done**
  * Pinned, checksummed open bundles.
  * Header-based detection.
  * Adapters for FlyWire v783 (open bundle and/or Codex files) and v630 (Shiu).
  * Planned adapters for BANC and male CNS, which refuse imports.
  * Canonical storage, manifests, validation reports and the synthetic fixture.
* **Executed on real data**
  * v783 imported and validated: 139,255 neurons / 15,091,983 connections / 54,492,922 synapses, every check passing; import takes 20 s.
  * v630 imported: 127,400 / 14,687,178 / 52,793,639.
  * Skeletons: 5.36 GB downloaded and indexed in 52 s.
* **Tests:** `test_ids_and_graph.py`, `test_fixture_and_import.py`, `tests/fulldata/`.
* **Remaining**
  * Codex-file import has been tested only with files that carry the real headers and synthetic rows. The Codex portal requires sign-in, so it was not exercised with real downloads.

## Phase 3: Brain simulation engine: complete

* **Done**
  * Numba and NumPy kernels plus a Brian2 reference.
  * Four modes, stimulation, silencing and lesions.
  * Threaded sessions with WebSocket streaming and recording.
* **Results**
  * Spike-for-spike identical to Brian2 on test networks.
  * Published v630 sugar-GRN → MN9 result reproduced (see [evidence](evidence/reproduction-shiu2024.md)).
* **Bugs found and fixed through testing**
  * Brian2's refractory semantics: input that arrives while a neuron is refractory is discarded.
  * Resume after single-stepping did not start the worker.
  * Lock starvation made controls lag by more than 1.5 s on the full brain; they now take 2–10 ms.
* **Remaining**
  * No GPU backend.
  * Trial-to-trial SD differs from the reference's at 200 Hz (4.8 vs 3.2 Hz); not investigated further.

## Phase 4: Brain Explorer 3D: complete

* **Done**
  * Point cloud of all neurons with colouring, legend, hemisphere filter, labels, ortho/perspective view and camera transitions.
  * Search, neuron details, partner tables, pathway tracing and subgraph export.
  * Skeleton LOD.
  * Activity overlay with scrubbing.
  * Links to the simulator.
* **Verification:** e2e test plus manual inspection on real data (screenshots); 120 fps with 139,255 points.
* **Remaining**
  * No neuropil meshes (no openly licensed FlyWire source).
  * No mesh (as opposed to skeleton) geometry.

## Phase 5: Virtual Fly baseline: complete

* **Done**
  * NeuroMechFly body, five arenas, sensors, baseline controller, streaming, mesh pack, recording and replay.
* **Verification:** integration tests (walking, turning convention, collisions, vision); e2e; screenshot.
* **Performance:** walking runs at 0.25× real time on CPU.

## Phase 6: Neural embodiment: complete (with a negative behavioural result)

* **Done:** bridge presets for the fixture and FlyWire v783, closed-loop sessions and perturbations.
* **Tests:** the full data flow is covered (`test_sensors_to_neurons_to_motor_and_back`, `test_neural_perturbation_changes_motor_output`, `test_zero_neural_output_means_no_walking`).
* **Bug found and fixed:** a descending neuron silenced by output block still counted in the motor readout.
* **Observed on FlyWire v783**
  * DM1 odour input drives DNa02-left but not P9, so the fly turns in place and does not approach the odour.
  * Silencing DNa02-left abolishes the turning drive. See [embodied evidence](evidence/embodied-flywire.md).
* **Scientific limitations:** the readout and encoding are assumptions, there is no ventral nerve cord, and gait comes from the CPG controller.

## Phase 7: Integrated experiment laboratory: complete

* **Done**
  * Ten templates, a background job runner, records with full provenance, comparison and export.
  * Experiments UI with charts and checks against published values.
  * Explorer → Simulator → Experiments workflow.
* **Tests:** `test_experiments.py`, e2e experiments test.

## Phase 8: Optimisation: partially complete

* **Done**
  * Event-driven CSR delivery, Numba `nogil` kernel and memory-mapped graph.
  * Server-side frame aggregation with backpressure; single-draw-call rendering.
  * Measured benchmarks (see [benchmarks](evidence/benchmarks.md)).
* **Not done**
  * Multithreaded or GPU kernels.
  * Active-set skipping of quiescent neurons (it would change results by snapping to rest, so it was not adopted).

## Phase 9: Documentation and release: mostly complete

* **Done**
  * README, tutorials 1–10, scientific, architecture, API, troubleshooting and evidence docs.
  * CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG, CITATION, LICENSE (MIT) and THIRD_PARTY_NOTICES.
  * CI and Pages workflows, Dependabot.
  * Static demo build verified locally.
* **CI**
  * Pushed and merged as PR #1. The first CI run exposed four problems, fixed in PR #8:
    * the retired `macos-14` runner;
    * missing headless OpenGL on Linux;
    * a GNU/BSD `mktemp` difference;
    * a flaky e2e test.
  * GitHub's macOS VMs cannot create an OpenGL context, so vision now degrades explicitly there.
  * CI passes on ubuntu-latest and macos-latest.
* **Blocked**
  * GitHub Pages deployment fails until Pages is enabled in the repository settings.
  * Fresh-clone setup was verified by cloning into a new directory on the same machine (`make setup`, `make test`, `make dev`); this found and fixed a bash 3.2 incompatibility in the launcher. It has not been tried on a second machine.

## Next steps

1. Enable GitHub Pages and confirm the static demo deploys.
2. Investigate the SD difference against the reference trials.
3. Add a BANC adapter, which would allow VNC-based motor readouts.
4. Explore a FlyVis integration in a separate Python 3.12 process.
5. Add a multithreaded kernel and an optional GPU backend, validated against Brian2.
