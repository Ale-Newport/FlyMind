# Neuron model

FlyMind's brain simulator implements the leaky integrate-and-fire (LIF) network of
**Shiu et al. (2024)**, *A Drosophila computational brain model reveals sensorimotor
processing*, Nature 634:210–219 (reference code:
[philshiu/Drosophila_brain_model](https://github.com/philshiu/Drosophila_brain_model),
inspected at `91bdd1e7`). The model and its parameters were reimplemented from the
reference code; no code was copied.

## Equations

Each neuron *i* is a point unit with membrane potential *v* and a synaptic drive *g*
(both in mV; *g* is a current-like variable, not a conductance):

$$
\tau_m \frac{dv_i}{dt} = v_0 - v_i + g_i + I_i \qquad\qquad
\tau_s \frac{dg_i}{dt} = -g_i
$$

* **Spike**: when $v_i > v_{th}$ and the neuron is not refractory.
* **Reset**: $v_i \leftarrow v_{reset}$, $g_i \leftarrow 0$; the neuron is refractory for
  $t_{ref}$ (both $v$ and $g$ are frozen).
* **Synaptic transmission**: a presynaptic spike of neuron *j* increments
  $g_i \mathrel{+}= w_{ij}$ after a fixed delay $t_{dly}$, with
  $w_{ij} = s_j \cdot n_{ij} \cdot w_{syn}$, where $n_{ij}$ is the number of
  reconstructed synapses from *j* to *i* and $s_j = \pm 1$ the sign assigned to *j*'s
  predicted neurotransmitter.
* **Poisson stimulation** (the reference model's activation method): each input spike
  adds $f_{poi} \cdot w_{syn} = 68.75$ mV directly to $v$; stimulated neurons have
  $t_{ref} = 0$, so each input spike produces an output spike on the next step.
* $I_i$ is a FlyMind extension (default 0) used for "current injection" experiments.

## Parameters

| Parameter | Value | Status | Source |
|---|---|---|---|
| $v_0$ (rest) | −52 mV | reference model | Shiu et al. 2024 (citing Kakaria & de Bivort 2017) |
| $v_{reset}$ | −52 mV | reference model | Shiu et al. 2024 |
| $v_{th}$ | −45 mV | reference model | Shiu et al. 2024 |
| $\tau_m$ | 20 ms | reference model | Shiu et al. 2024 ($R C = 10\,M\Omega \times 2\,nF$) |
| $\tau_s$ | 5 ms | reference model | Shiu et al. 2024 (citing Jürgensen et al. 2021) |
| $t_{ref}$ | 2.2 ms | reference model | Shiu et al. 2024 (citing Lazar et al. 2021) |
| $t_{dly}$ | 1.8 ms | reference model | Shiu et al. 2024 (citing Paul et al. 2015) |
| $w_{syn}$ | 0.275 mV | **tuned free parameter** | Shiu et al. 2024 |
| $f_{poi}$ | 250 | **tuned** | Shiu et al. 2024 ("sufficient to cause spiking") |
| $\Delta t$ | 0.1 ms | reference model | Brian2 default used by the reference |

All values, with their status, are served by `GET /api/brain/params` and shown in the
simulator UI ("est." marks tuned parameters). **None of these is a measurement of the
neurons being simulated**: the same parameters are applied to every neuron, and
synapse count is used as a proxy for synaptic strength.

## Numerical scheme

The subthreshold system is linear, so FlyMind integrates it exactly with one-step
propagators (identical to Brian2's `method='linear'`):

$$
g(t+\Delta t) = g\,e^{-\Delta t/\tau_s},\quad
u(t+\Delta t) = u\,e^{-\Delta t/\tau_m} + g\,\frac{\tau_s}{\tau_s-\tau_m}
\left(e^{-\Delta t/\tau_s} - e^{-\Delta t/\tau_m}\right),\quad u = v - v_0 - I
$$

Per time step, operations follow Brian2's default schedule: (1) state update,
(2) threshold, (3) synaptic delivery and external input, (4) reset.

**Refractory semantics.** Brian2 implements `(unless refractory)` as a *conditional
write* that also applies to synaptic and Poisson updates. Input that arrives while a
neuron is refractory (including the step in which it spikes) is therefore discarded.
FlyMind reproduces this (`drop_input_during_refractory`), and the refractory window is
`floor(t_ref/dt + 1e-3) = 22` steps measured from the spike step, exactly as
Brian2's `timestep(t - lastspike) >= timestep(t_ref)`.

## Engines

| Engine | Use | Notes |
|---|---|---|
| `numba` (default) | interactive sessions, experiments, full brain | event-driven CSR delivery, `nogil` |
| `numpy` | independent reference for testing the compiled kernel | identical semantics, slower |
| Brian2 (`flymind.brain.brian2_engine`) | validation against the reference simulator | builds the reference equations; receives the same pre-generated input spikes |

Equivalence is tested in `tests/unit/test_brian2_equivalence.py` (identical spike
trains, membrane potentials equal within 1e-9 mV) and `tests/unit/test_lif_dynamics.py`
(analytic threshold-crossing times, PSP shape, delays, refractoriness).

## Randomness and reproducibility

Poisson inputs are drawn per block of 1,000 steps from `SeedSequence([seed, block])`, so
results depend only on the seed and the stimulation schedule, not on how the
simulation is chunked (interactive stepping and batch runs give identical spikes). The
reference code sets no seed; FlyMind's runs are deterministic. Experiments use
"common random numbers": trial *k* uses seed `base + k` in every condition.
