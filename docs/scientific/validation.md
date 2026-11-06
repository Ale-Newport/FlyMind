# Validation

| What | How | Where | Status |
|---|---|---|---|
| LIF analytics (threshold time under constant drive, ISI) | closed-form comparison, exact step | `tests/unit/test_lif_dynamics.py` | passing |
| PSP shape after one synaptic event | closed-form bi-exponential, 1e-9 mV tolerance | same | passing |
| Synaptic delay, sign, propagation latency per hop | exact step equality vs analytic crossing time | `tests/integration/test_explorer_to_simulator.py` | passing |
| Reset, refractory window (22 steps), zero refractory for stimulated neurons | state traces | `test_lif_dynamics.py` | passing |
| Input dropped during refractoriness (Brian2 conditional write) | dedicated test | `test_lif_dynamics.py` | passing |
| Determinism and chunking independence | identical spike trains for 1 × 3000 vs 1+999+1500+500 steps; seed sensitivity | `test_lif_dynamics.py` | passing |
| Numba vs NumPy kernels | identical spikes, membrane potentials within 1e-12 mV | `test_lif_dynamics.py` | passing |
| float32 vs float64 | readout counts within 5 % | `test_lif_dynamics.py` | passing |
| **Engine equivalence with Brian2** (reference simulator) | identical spike trains, potentials within 1e-9 mV, incl. current stimuli, silencing, scaling, sub-networks | `tests/unit/test_brian2_equivalence.py` | passing |
| **Reproduction of a published result** | Shiu et al. 2024 sugar GRN → MN9 on the exact v630 network, 30 trials | [evidence](../evidence/reproduction-shiu2024.md) | reproduced |
| Dataset integrity | 16 checks per import (IDs, CSR, signs, totals, coordinates, expected counts) | `validation_report.md` per dataset; `tests/unit/test_fixture_and_import.py` | passing (v783, v630, fixture) |
| v783 statistics | 139,255 neurons; 15,091,983 edges; 54,492,922 synapses | `tests/fulldata/test_flywire783.py` | passing |
| Closed loop (sensor → neuron → motor → body → sensor) | integration tests on the fixture | `tests/integration/test_closed_loop.py` | passing |

## Tolerances and expected differences

* FlyMind and Brian2 use the same exact propagators; differences are floating-point
  rounding of the order of 1e-13 mV, which never changed a threshold crossing in the tests.
  In very long runs a rounding difference could in principle flip a crossing; spike-train
  identity is therefore asserted on test networks, and agreement on large networks is
  assessed statistically (reproduction).
* The reproduction uses different random input streams than the reference (which is
  unseeded), so agreement is statistical: mean MN9 rate within ±3 Hz (200 Hz drive) and
  ±4 Hz (100 Hz drive) of the reference's 30-trial means.
