"""LIF network engine: network selection, interventions, stimulation and stepping."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from flymind.brain.kernels import advance_numba, advance_numpy
from flymind.brain.params import LIFParams
from flymind.brain.stimulus import (
    CurrentStimulus,
    PoissonStimulus,
    PulseTrainStimulus,
    Silencing,
    SynapticScaling,
    generate_input_events,
)
from flymind.connectome.graph import SparseGraph

Backend = Literal["numba", "numpy"]
EVENT_BLOCK_STEPS = 1000  # Poisson events are drawn per block -> chunking-independent results


@dataclass
class BrainNetwork:
    """The (sub)network being simulated.

    ``global_idx[k]`` is the dataset idx of engine-local neuron k; ``local_of`` is
    the inverse map over the whole dataset (-1 = not simulated).
    """

    graph: SparseGraph
    global_idx: np.ndarray
    local_of: np.ndarray
    mode: str = "full"

    @classmethod
    def full(cls, graph: SparseGraph, mode: str = "full") -> BrainNetwork:
        g = SparseGraph(
            graph.n,
            np.ascontiguousarray(graph.indptr, dtype=np.int64),
            np.ascontiguousarray(graph.indices, dtype=np.int32),
            np.ascontiguousarray(graph.syn_count, dtype=np.int32),
            np.ascontiguousarray(graph.sign, dtype=np.int8),
        )
        idx = np.arange(graph.n, dtype=np.int64)
        return cls(g, idx, idx.copy(), mode)

    @classmethod
    def subset(cls, graph: SparseGraph, nodes: np.ndarray, mode: str = "circuit") -> BrainNetwork:
        sub, global_idx = graph.subgraph(nodes)
        local_of = np.full(graph.n, -1, dtype=np.int64)
        local_of[global_idx] = np.arange(len(global_idx))
        return cls(sub, global_idx.astype(np.int64), local_of, mode)

    @property
    def n(self) -> int:
        return self.graph.n


@dataclass
class ChunkResult:
    t0_step: int
    n_steps: int
    spike_steps: np.ndarray  # int64 absolute step
    spike_local: np.ndarray  # int64 engine-local idx
    probe_steps: np.ndarray
    probe_v: np.ndarray  # (rows, n_probes)
    probe_g: np.ndarray


@dataclass
class EngineState:
    v: np.ndarray
    g: np.ndarray
    last_spike: np.ndarray
    ring: np.ndarray
    ring_count: np.ndarray
    t_step: int = 0


@dataclass
class LIFEngine:
    network: BrainNetwork
    params: LIFParams = field(default_factory=LIFParams)
    seed: int = 0
    backend: Backend = "numba"
    probe_local: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    probe_every: int = 1

    def __post_init__(self) -> None:
        self.stimuli: list[PoissonStimulus | PulseTrainStimulus | CurrentStimulus] = []
        self.interventions: list[Silencing | SynapticScaling] = []
        self._dtype = np.float64 if self.params.precision == "float64" else np.float32
        self._event_cache: tuple[int, int, tuple] | None = None
        self.probe_local = np.asarray(self.probe_local, dtype=np.int64)
        self._recompute_weights()
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = int(seed)
        n, p = self.network.n, self.params
        self.state = EngineState(
            v=np.full(n, p.v_rest_mV, dtype=self._dtype),
            g=np.zeros(n, dtype=self._dtype),
            last_spike=np.full(n, -(10**9), dtype=np.int64),
            ring=np.zeros((p.delay_steps + 1, n), dtype=np.int64),
            ring_count=np.zeros(p.delay_steps + 1, dtype=np.int64),
        )
        self._event_cache = None

    @property
    def t_step(self) -> int:
        return self.state.t_step

    @property
    def t_ms(self) -> float:
        return self.state.t_step * self.params.dt_ms

    # ---------------------------------------------------- stimuli/interventions
    def set_stimuli(self, stimuli: list) -> None:
        self.stimuli = list(stimuli)
        self._event_cache = None

    def add_stimulus(self, stim) -> None:
        self.stimuli.append(stim)
        self._event_cache = None

    def remove_stimulus(self, stim_id: str) -> bool:
        before = len(self.stimuli)
        self.stimuli = [s for s in self.stimuli if s.id != stim_id]
        self._event_cache = None
        return len(self.stimuli) != before

    def set_interventions(self, interventions: list) -> None:
        self.interventions = list(interventions)
        self._recompute_weights()

    def add_intervention(self, item) -> None:
        self.interventions.append(item)
        self._recompute_weights()

    def remove_intervention(self, item_id: str) -> bool:
        before = len(self.interventions)
        self.interventions = [i for i in self.interventions if i.id != item_id]
        self._recompute_weights()
        return len(self.interventions) != before

    def _recompute_weights(self) -> None:
        """Effective weights from pristine counts; interventions never mutate the graph."""
        g = self.network.graph
        p = self.params
        w = g.sign.astype(np.float64) * g.syn_count.astype(np.float64) * p.w_syn_mV
        clamped = np.zeros(g.n, dtype=np.bool_)
        lo = self.network.local_of
        pre_of_edge: np.ndarray | None = None
        for item in self.interventions:
            if isinstance(item, Silencing):
                tgt = lo[np.asarray(item.targets, dtype=np.int64)]
                tgt = tgt[tgt >= 0]
                if item.mode == "clamp":
                    clamped[tgt] = True
                for i in tgt:
                    w[g.indptr[i] : g.indptr[i + 1]] = 0.0
            elif isinstance(item, SynapticScaling):
                if pre_of_edge is None:
                    pre_of_edge = g.pre_indices()
                pre = lo[np.asarray(item.pre, dtype=np.int64)]
                mask = np.isin(pre_of_edge, pre[pre >= 0])
                if item.post is not None:
                    post = lo[np.asarray(item.post, dtype=np.int64)]
                    mask &= np.isin(g.indices, post[post >= 0])
                w[mask] *= item.factor
        self.weights = w.astype(self._dtype)
        self.clamped = clamped

    def _ref_steps(self) -> np.ndarray:
        ref = np.full(self.network.n, self.params.refractory_steps, dtype=np.int64)
        if self.params.stimulated_refractory_zero:
            lo = self.network.local_of
            for stim in self.stimuli:
                if isinstance(stim, PoissonStimulus | PulseTrainStimulus):
                    tgt = lo[np.asarray(stim.targets, dtype=np.int64)]
                    ref[tgt[tgt >= 0]] = 0
        return ref

    def _drive_at(self, t_ms: float) -> np.ndarray:
        drive = np.zeros(self.network.n, dtype=self._dtype)
        lo = self.network.local_of
        for stim in self.stimuli:
            if isinstance(stim, CurrentStimulus):
                if any(a <= t_ms < b for a, b in stim.windows()):
                    tgt = lo[np.asarray(stim.targets, dtype=np.int64)]
                    drive[tgt[tgt >= 0]] += stim.amplitude_mV
        return drive

    def _current_boundaries(self) -> list[int]:
        out = set()
        for stim in self.stimuli:
            if isinstance(stim, CurrentStimulus):
                for a, b in stim.windows():
                    out.add(int(round(a / self.params.dt_ms)))
                    if np.isfinite(b):
                        out.add(int(round(b / self.params.dt_ms)))
        return sorted(out)

    def _events(self, t0: int, n_steps: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        spiking = [s for s in self.stimuli if isinstance(s, PoissonStimulus | PulseTrainStimulus)]
        if not spiking:
            z = np.zeros(0, dtype=np.int64)
            return z, z, np.zeros(0, dtype=self._dtype)
        parts = []
        b0, b1 = t0 // EVENT_BLOCK_STEPS, (t0 + n_steps - 1) // EVENT_BLOCK_STEPS
        for b in range(b0, b1 + 1):
            if self._event_cache is not None and self._event_cache[0] == b:
                ev = self._event_cache[2]
            else:
                rng = np.random.default_rng(np.random.SeedSequence([self.seed, b]))
                ev = generate_input_events(
                    spiking,
                    self.network.local_of,
                    b * EVENT_BLOCK_STEPS,
                    EVENT_BLOCK_STEPS,
                    self.params.dt_ms,
                    self.params.w_syn_mV,
                    self.params.poisson_weight_factor,
                    rng,
                )
                self._event_cache = (b, 0, ev)
            parts.append(ev)
        steps = np.concatenate([p[0] for p in parts])
        idx = np.concatenate([p[1] for p in parts])
        w = np.concatenate([p[2] for p in parts])
        keep = (steps >= t0) & (steps < t0 + n_steps)
        return steps[keep], idx[keep], w[keep].astype(self._dtype)

    # ------------------------------------------------------------------- run
    def run(self, n_steps: int, extra_events: tuple | None = None) -> ChunkResult:
        """Advance ``n_steps``; returns spikes and probe samples for this chunk.

        ``extra_events`` = (steps, local_idx, weight) are additional input spikes (added
        to v like Poisson input) supplied by a caller such as the sensory encoder of the
        neural-body bridge; they must lie within this chunk.
        """
        if n_steps <= 0:
            raise ValueError("n_steps must be positive")
        t_start = self.state.t_step
        bounds = [b for b in self._current_boundaries() if t_start < b < t_start + n_steps]
        edges = [t_start, *bounds, t_start + n_steps]
        results = [
            self._run_segment(a, b - a, extra_events)
            for a, b in zip(edges[:-1], edges[1:], strict=True)
        ]
        return ChunkResult(
            t_start,
            n_steps,
            np.concatenate([r.spike_steps for r in results]),
            np.concatenate([r.spike_local for r in results]),
            np.concatenate([r.probe_steps for r in results]),
            np.concatenate([r.probe_v for r in results]),
            np.concatenate([r.probe_g for r in results]),
        )

    def _run_segment(self, t0: int, n_steps: int, extra_events: tuple | None = None) -> ChunkResult:
        p, st, net = self.params, self.state, self.network
        a_vv, a_vg, a_gg = p.propagators()
        drive = self._drive_at(t0 * p.dt_ms)
        ext_steps, ext_idx, ext_w = self._events(t0, n_steps)
        if extra_events is not None and len(extra_events[0]):
            xs, xi, xw = (np.asarray(a) for a in extra_events)
            keep = (xs >= t0) & (xs < t0 + n_steps)
            ext_steps = np.concatenate([ext_steps, xs[keep].astype(np.int64)])
            ext_idx = np.concatenate([ext_idx, xi[keep].astype(np.int64)])
            ext_w = np.concatenate([ext_w, xw[keep].astype(self._dtype)])
            order = np.lexsort((ext_idx, ext_steps))
            ext_steps, ext_idx, ext_w = ext_steps[order], ext_idx[order], ext_w[order]
        kernel = advance_numba if self.backend == "numba" else advance_numpy
        n_probe = len(self.probe_local)
        cap = max(4 * net.n, 65536)
        spk_steps_l, spk_idx_l, pr_steps_l, pr_v_l, pr_g_l = [], [], [], [], []
        done = 0
        while done < n_steps:
            todo = n_steps - done
            out_steps = np.empty(cap, dtype=np.int64)
            out_idx = np.empty(cap, dtype=np.int64)
            rows = (todo // self.probe_every + 2) if n_probe else 0
            probe_v = np.empty((rows, n_probe), dtype=self._dtype)
            probe_g = np.empty((rows, n_probe), dtype=self._dtype)
            tcur = t0 + done
            first_probe = tcur + (-tcur) % self.probe_every
            sel = ext_steps >= tcur
            n_done, n_out, n_rows, _overflow = kernel(
                todo,
                tcur,
                st.v,
                st.g,
                st.last_spike,
                drive,
                self.clamped,
                net.graph.indptr,
                net.graph.indices,
                self.weights,
                st.ring,
                st.ring_count,
                p.delay_steps,
                ext_steps[sel],
                ext_idx[sel],
                ext_w[sel],
                True,
                self._dtype(a_vv),
                self._dtype(a_vg),
                self._dtype(a_gg),
                self._dtype(p.v_rest_mV),
                self._dtype(p.v_reset_mV),
                self._dtype(p.v_threshold_mV),
                self._ref_steps(),
                p.hold_g_during_refractory,
                p.reset_g,
                p.drop_input_during_refractory,
                out_steps,
                out_idx,
                self.probe_local,
                self.probe_every,
                probe_v,
                probe_g,
            )
            spk_steps_l.append(out_steps[:n_out].copy())
            spk_idx_l.append(out_idx[:n_out].copy())
            if n_rows:
                pr_steps_l.append(first_probe + self.probe_every * np.arange(n_rows))
                pr_v_l.append(probe_v[:n_rows].copy())
                pr_g_l.append(probe_g[:n_rows].copy())
            done += int(n_done)
            st.t_step = t0 + done
            if int(n_done) == 0 and n_out == 0:
                cap *= 2
        empty_pr = np.zeros((0, n_probe), dtype=self._dtype)
        return ChunkResult(
            t0,
            n_steps,
            np.concatenate(spk_steps_l) if spk_steps_l else np.zeros(0, np.int64),
            np.concatenate(spk_idx_l) if spk_idx_l else np.zeros(0, np.int64),
            np.concatenate(pr_steps_l) if pr_steps_l else np.zeros(0, np.int64),
            np.concatenate(pr_v_l) if pr_v_l else empty_pr,
            np.concatenate(pr_g_l) if pr_g_l else empty_pr,
        )
