# Feature verification matrix

Status key: **verified** = executed test or evidence file in this repository; **manual**
= inspected in the running application (screenshot recorded); **blocked** = could not be
verified, with the reason; **not implemented** = deliberately absent.
All verification was done at commit `a4e2bcd` on macOS 27.0.1, Apple M2 Max.

## Brain Simulator

| Requirement | Status | Evidence |
|---|---|---|
| LIF engine with documented equations | verified | `docs/scientific/neuron-model.md`; `test_lif_dynamics.py` |
| Real FlyWire connections imported and simulated (full brain, 139,255 neurons) | verified | `validation_report.md` (v783); `tests/fulldata/test_flywire783.py`; benchmarks |
| Circuit, region, full-brain, demonstration modes | verified | `brain/session.py::build_network`; API test; e2e (demo); screenshots (full) |
| Stimulate by ID, cell type, region, transmitter, connectivity, saved group | verified | `connectome/selectors.py`; API/e2e tests use groups and IDs |
| Poisson, pulse-train, current, scheduled and repeated stimuli | verified | `test_lif_dynamics.py`; `repeated_stimuli` template |
| Silencing (output block, clamp) and reversible synaptic perturbation, restore original | verified | `test_silencing_and_reversible_lesions` |
| Start/pause/resume/stop/reset/step/speed, seed, duration, save/export | verified | API test; e2e simulator test; screenshot |
| Sim time vs wall time displayed; no real-time claim | manual | screenshot `simulator-flywire-783-sugar.png` (0.42×) |
| Raster, traces, population rates, regional activity, before/after snapshot | manual + e2e | e2e asserts raster/population; screenshot |
| Brian2 equivalence | verified | `test_brian2_equivalence.py` (identical spikes) |
| Reproduction of a published result | **reproduced** | `reproduction-shiu2024.md` |
| 8 experiment templates | verified | `test_every_template_builds_for_the_fixture`; real-data runs in `docs/evidence` |

## Brain Explorer 3D

| Requirement | Status | Evidence |
|---|---|---|
| Whole-brain anatomical view (139,255 neurons), orbit/zoom/pan/reset, ortho/perspective | manual | screenshots; e2e canvas |
| Colour by region, cell type, transmitter, super class, hemisphere; transparency; legend toggles | manual | UI; screenshot |
| Real skeletons (FlyWire v783, Zenodo CC BY 4.0) with LOD; geometry-unavailable message otherwise | verified + manual | `test_skeleton_geometry_if_installed`; e2e asserts the synthetic message; screenshot DNa02 |
| Neuron metadata, inputs/outputs with synapse counts and signs, Codex link | verified | API tests; e2e |
| Find partners, trace pathways, depth, synapse filter, export subgraph | verified | API test (pathway sugar GRN→MN9 in full-data test); CSV endpoint |
| Simulation overlay with time-window scrubbing | manual | screenshot `explorer-flywire-783-activity-overlay.png` |
| Select in 3D → stimulate/silence/record in simulator | verified (e2e) | e2e explorer test; screenshot |
| Efficient rendering | verified | 120 fps (display-capped) with 139,255 points; single draw call |
| Neuropil meshes | not implemented | no openly licensed FlyWire per-neuropil meshes; labels at medians instead |

## Virtual Fly

| Requirement | Status | Evidence |
|---|---|---|
| Official NeuroMechFly v2 body (head, eyes, antennae, thorax, abdomen, wings, 6 legs) in MuJoCo | verified + manual | 69 mesh geoms streamed; screenshot |
| Baseline controller (FlyGym HybridTurningController) | verified | `test_baseline_walks_and_turns_left_for_positive_turn` |
| Five arenas (empty, food, obstacle, light, experimental) with reset | verified | integration tests (empty/obstacle/light/food), e2e (obstacle), UI editor |
| Sensors: odour, vision (ommatidia), obstacle contact, food contact, joints, orientation | verified | `test_sensors_to_neurons_to_motor_and_back`, `test_obstacle_contact_is_sensed`, `test_recording_save_and_replay_files` |
| Documented neural→motor and sensor→neural interfaces | verified | `bridge.py`; `neural-body-interface.md` |
| Neural perturbation changes motor output | verified | `test_neural_perturbation_changes_motor_output` |
| No hidden scripted drive; zero neural output → no walking | verified | `test_zero_neural_output_means_no_walking` |
| Recording, replay, export | verified + manual | save/replay test; UI replay |
| Behavioural metrics (distance, speed, heading, collisions, neural, motor, joints, time) | verified | `FlySession.metrics`; embodied evidence |
| FlyVis visual network | not implemented | Python < 3.13 requirement (ADR 0007) |
| Touch mapping for FlyWire | not implemented | no VNC in FAFB (documented) |

## Integration and engineering

| Requirement | Status | Evidence |
|---|---|---|
| Neuron selected in explorer starts an experiment | verified | e2e explorer→simulator |
| Simulated spike produces expected downstream events (test circuit) | verified | `test_selected_neuron_drives_downstream_chain` (exact analytic latency) |
| Neural outputs reach the motor interface; body movement changes sensors; sensors feed back | verified | `test_sensors_to_neurons_to_motor_and_back` |
| Saved experiments replay; exports load and analyse | verified | `test_run_persists_reproducible_records` |
| Fresh-clone demo without credentials | verified | e2e runs against a fresh data root with only the fixture |
| One-command setup and launch | verified (fresh clone) | [test results → fresh-clone check](test-results.md) |
| Pinned dependencies and lockfiles | verified | `uv.lock`, `apps/web/package-lock.json` |
| CI | verified (GitHub Actions) | PR #8 at `6f88593`: Python on ubuntu-latest and macos-latest, and Web (type check, unit, Playwright e2e), all passing. On macOS runners (no OpenGL) the vision test is designed to skip with a reason; the passing job's log was not read |
| GitHub Pages static demo | built (CI), **not deployed** | the Pages build job succeeds; deployment fails until Pages is enabled in the repository settings |
| Safari | **not tested** | only Chromium is automated |
| Linux | verified in CI | ubuntu-latest: full non-data suite including MuJoCo vision via Mesa EGL, and Playwright e2e |
| BANC / male CNS | planned | adapters refuse imports until validated |
