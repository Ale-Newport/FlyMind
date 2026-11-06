"""Stimulation and intervention specifications.

Each stimulus approximates a class of biological experiment (documented in
docs/scientific/interventions.md):

* ``PoissonStimulus``   - optogenetic/thermogenetic activation (e.g. CsChrimson,
  TrpA1): Poisson spike trains delivered to the targets (Shiu et al. 2024 method).
* ``PulseTrainStimulus`` - regular, frequency-locked stimulation (e.g. pulsed light).
* ``CurrentStimulus``   - intracellular current injection (FlyMind extension;
  enters as a constant drive term, in mV, i.e. R_m * I).
* ``Silencing``         - genetic silencing. ``block_output`` removes the neuron's
  synaptic output (like tetanus toxin; the reference model's method); ``clamp``
  holds the membrane at rest and prevents spikes (like Kir2.1 hyperpolarisation).
* ``SynapticScaling``   - reversible scaling of selected connections (factor 0 is a
  connection-specific lesion).

Interventions never modify the stored connectome; effective weights are recomputed
from the pristine synapse counts every time interventions change.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


class _Timed(BaseModel):
    id: str = Field(default_factory=_new_id)
    targets: list[int] = Field(description="dataset idx of target neurons")
    start_ms: float = 0.0
    stop_ms: float | None = None
    repeats: int = Field(1, ge=1, description="number of repetitions of the on-window")
    interval_ms: float = Field(0.0, ge=0, description="onset-to-onset interval for repeats")
    label: str = ""

    def windows(self) -> list[tuple[float, float]]:
        stop = self.stop_ms if self.stop_ms is not None else float("inf")
        width = stop - self.start_ms
        if self.repeats > 1 and (self.interval_ms <= 0 or not np.isfinite(width)):
            raise ValueError("repeated stimuli need a finite stop_ms and interval_ms > 0")
        return [
            (self.start_ms + k * self.interval_ms, self.start_ms + k * self.interval_ms + width)
            for k in range(self.repeats)
        ]


class PoissonStimulus(_Timed):
    kind: Literal["poisson"] = "poisson"
    rate_hz: float = Field(150.0, ge=0, le=1000)
    weight_factor: float | None = Field(
        None, description="override LIFParams.poisson_weight_factor for this stimulus"
    )


class PulseTrainStimulus(_Timed):
    kind: Literal["pulse_train"] = "pulse_train"
    frequency_hz: float = Field(50.0, gt=0, le=1000)
    weight_factor: float | None = None


class CurrentStimulus(_Timed):
    kind: Literal["current"] = "current"
    amplitude_mV: float = Field(10.0, ge=-100, le=100, description="R_m * I, in mV")


Stimulus = Annotated[
    PoissonStimulus | PulseTrainStimulus | CurrentStimulus, Field(discriminator="kind")
]


class Silencing(BaseModel):
    kind: Literal["silence"] = "silence"
    id: str = Field(default_factory=_new_id)
    targets: list[int]
    mode: Literal["block_output", "clamp"] = "block_output"
    label: str = ""


class SynapticScaling(BaseModel):
    kind: Literal["synaptic_scaling"] = "synaptic_scaling"
    id: str = Field(default_factory=_new_id)
    pre: list[int] = Field(description="presynaptic idx")
    post: list[int] | None = Field(None, description="postsynaptic idx (None = all targets)")
    factor: float = Field(0.0, ge=0, le=10)
    label: str = ""


Intervention = Annotated[Silencing | SynapticScaling, Field(discriminator="kind")]


def generate_input_events(
    stimuli: list[PoissonStimulus | PulseTrainStimulus],
    local_of: np.ndarray,
    step0: int,
    n_steps: int,
    dt_ms: float,
    w_syn: float,
    default_factor: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """External spike events in [step0, step0+n_steps) as (step, local_idx, weight), sorted.

    Poisson trains are Bernoulli(rate*dt) per step, matching Brian2's PoissonGroup.
    ``local_of`` maps dataset idx -> engine-local idx (-1 if not simulated).
    Random numbers are drawn chunk by chunk from ``rng`` so results are reproducible
    for a given seed and chunk schedule.
    """
    steps_l, idx_l, w_l = [], [], []
    t_lo, t_hi = step0, step0 + n_steps
    for stim in stimuli:
        tgt = local_of[np.asarray(stim.targets, dtype=np.int64)]
        tgt = tgt[tgt >= 0]
        if len(tgt) == 0:
            continue
        factor = default_factor if stim.weight_factor is None else stim.weight_factor
        weight = factor * w_syn
        for w_start, w_stop in stim.windows():
            a = max(t_lo, int(round(w_start / dt_ms)))
            b = min(t_hi, int(round(w_stop / dt_ms)) if np.isfinite(w_stop) else t_hi)
            if b <= a:
                continue
            if isinstance(stim, PoissonStimulus):
                p = stim.rate_hz * dt_ms * 1e-3
                hits = rng.random((b - a, len(tgt))) < p
                si, ti = np.nonzero(hits)
                steps_l.append(si.astype(np.int64) + a)
                idx_l.append(tgt[ti])
            else:
                period = max(1, int(round(1000.0 / stim.frequency_hz / dt_ms)))
                first = int(round(w_start / dt_ms))
                k0 = max(0, -(-(a - first) // period))
                ticks = np.arange(first + k0 * period, b, period, dtype=np.int64)
                ticks = ticks[ticks >= a]
                steps_l.append(np.repeat(ticks, len(tgt)))
                idx_l.append(np.tile(tgt, len(ticks)))
            w_l.append(np.full(len(steps_l[-1]), weight, dtype=np.float64))
    if not steps_l:
        z = np.zeros(0, dtype=np.int64)
        return z, z, np.zeros(0, dtype=np.float64)
    steps = np.concatenate(steps_l)
    idx = np.concatenate(idx_l).astype(np.int64)
    w = np.concatenate(w_l)
    order = np.lexsort((idx, steps))
    return steps[order], idx[order], w[order]
