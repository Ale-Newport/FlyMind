"""Interactive simulation sessions (background thread, controls, live stimulation, streaming).

A session owns one :class:`LIFEngine` and advances it in chunks on a worker thread.
Control actions (start/pause/resume/step/stop/reset, stimuli, interventions,
speed) are applied between chunks and appended to an action log with the simulated
time at which they took effect, so an interactive session can be replayed exactly.
"""

from __future__ import annotations

import collections
import threading
import time
import uuid
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from flymind.brain.engine import Backend, BrainNetwork, LIFEngine
from flymind.brain.params import LIFParams
from flymind.brain.recording import SpikeRecord, grouped_activity
from flymind.brain.stimulus import (
    CurrentStimulus,
    PoissonStimulus,
    PulseTrainStimulus,
    Silencing,
    SynapticScaling,
)
from flymind.common.concurrency import YieldingLock
from flymind.common.logging import get_logger
from flymind.common.provenance import utc_now
from flymind.connectome.selectors import NeuronSelector, resolve
from flymind.connectome.store import ConnectomeStore, get_store

log = get_logger("brain.session")

Mode = Literal["full", "circuit", "region", "demo"]
MAX_SESSION_NEURONS_CIRCUIT = 50_000


class NetworkConfig(BaseModel):
    mode: Mode = "full"
    selection: NeuronSelector | None = Field(None, description="circuit mode: seed neurons")
    expand_depth: int = Field(0, ge=0, le=4)
    expand_direction: Literal["downstream", "upstream", "both"] = "downstream"
    expand_min_syn: int = Field(5, ge=1)
    neuropils: list[str] = Field(default_factory=list, description="region mode")
    max_neurons: int = Field(MAX_SESSION_NEURONS_CIRCUIT, ge=1, le=200_000)


class StimulusSpec(BaseModel):
    """A stimulus addressed by selector (resolved against the dataset at apply time)."""

    kind: Literal["poisson", "pulse_train", "current"] = "poisson"
    selector: NeuronSelector
    rate_hz: float = Field(150.0, ge=0, le=1000)
    frequency_hz: float = Field(50.0, gt=0, le=1000)
    amplitude_mV: float = Field(10.0, ge=-100, le=100)
    start_ms: float = Field(0.0, ge=0)
    stop_ms: float | None = None
    repeats: int = Field(1, ge=1, le=1000)
    interval_ms: float = Field(0.0, ge=0)
    weight_factor: float | None = Field(None, ge=0, le=10_000)
    label: str = ""

    def to_stimulus(self, targets: list[int], offset_ms: float = 0.0):
        common = dict(
            targets=targets,
            start_ms=self.start_ms + offset_ms,
            stop_ms=None if self.stop_ms is None else self.stop_ms + offset_ms,
            repeats=self.repeats,
            interval_ms=self.interval_ms,
            label=self.label,
        )
        if self.kind == "poisson":
            return PoissonStimulus(rate_hz=self.rate_hz, weight_factor=self.weight_factor, **common)
        if self.kind == "pulse_train":
            return PulseTrainStimulus(
                frequency_hz=self.frequency_hz, weight_factor=self.weight_factor, **common
            )
        return CurrentStimulus(amplitude_mV=self.amplitude_mV, **common)


class InterventionSpec(BaseModel):
    kind: Literal["silence", "synaptic_scaling"] = "silence"
    selector: NeuronSelector
    post_selector: NeuronSelector | None = None
    mode: Literal["block_output", "clamp"] = "block_output"
    factor: float = Field(0.0, ge=0, le=10)
    label: str = ""

    def to_intervention(self, targets: list[int], post: list[int] | None):
        if self.kind == "silence":
            return Silencing(targets=targets, mode=self.mode, label=self.label)
        return SynapticScaling(pre=targets, post=post, factor=self.factor, label=self.label)


class SessionConfig(BaseModel):
    dataset_id: str
    network: NetworkConfig = NetworkConfig()
    params: LIFParams = LIFParams()
    seed: int = Field(0, ge=0, le=2**31 - 1)
    backend: Backend = "numba"
    probe_root_ids: list[int] = Field(default_factory=list, max_length=64)
    probe_every_steps: int = Field(10, ge=1, le=1000)
    max_duration_ms: float = Field(60_000.0, gt=0, le=600_000)
    chunk_ms: float = Field(10.0, gt=0, le=1000)
    speed: float | None = Field(None, gt=0, le=1000, description="target sim/wall ratio")
    stimuli: list[StimulusSpec] = Field(default_factory=list)
    interventions: list[InterventionSpec] = Field(default_factory=list)
    label: str = ""


def build_network(store: ConnectomeStore, cfg: NetworkConfig) -> BrainNetwork:
    graph = store.graph
    if cfg.mode == "demo":
        if not store.manifest.synthetic:
            raise ValueError("demo mode runs only on synthetic fixture datasets")
        return BrainNetwork.full(graph, mode="demo")
    if cfg.mode == "full":
        if store.manifest.synthetic:
            return BrainNetwork.full(graph, mode="demo")
        return BrainNetwork.full(graph, mode="full")
    if cfg.mode == "circuit":
        if cfg.selection is None or cfg.selection.is_empty():
            raise ValueError("circuit mode needs a neuron selection")
        seeds = resolve(store, cfg.selection)
        if len(seeds) == 0:
            raise ValueError("circuit selection matched no neurons")
        nodes = set(seeds.tolist())
        if cfg.expand_depth:
            nodes |= set(
                store.queries.neighborhood(
                    seeds,
                    cfg.expand_depth,
                    cfg.expand_direction,
                    cfg.expand_min_syn,
                    cfg.max_neurons,
                ).keys()
            )
        return BrainNetwork.subset(graph, np.array(sorted(nodes))[: cfg.max_neurons], "circuit")
    if cfg.mode == "region":
        if not cfg.neuropils:
            raise ValueError("region mode needs at least one neuropil")
        idx = resolve(store, NeuronSelector(neuropils=cfg.neuropils))
        if len(idx) == 0:
            raise ValueError("no neurons have their primary neuropil in the selected regions")
        if len(idx) > cfg.max_neurons:
            raise ValueError(f"region selection has {len(idx)} neurons > max_neurons")
        return BrainNetwork.subset(graph, idx, "region")
    raise ValueError(f"unknown mode {cfg.mode}")


Status = Literal["ready", "running", "paused", "stopped", "finished", "error", "external"]


class SimulationSession:
    def __init__(self, config: SessionConfig, store: ConnectomeStore | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.config = config
        self.store = store or get_store(config.dataset_id)
        self.created_at = utc_now()
        self.network = build_network(self.store, config.network)
        self.root_ids = self.store.neurons["root_id"].to_numpy(dtype=np.int64)
        self.status: Status = "ready"
        self.error: str | None = None
        self._lock = YieldingLock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._stop_flag = False
        self._subscribers: list[collections.deque] = []
        self.actions: list[dict] = []
        self.stimulus_specs: dict[str, StimulusSpec] = {}
        self.intervention_specs: dict[str, InterventionSpec] = {}
        self.engine = LIFEngine(
            self.network,
            config.params,
            seed=config.seed,
            backend=config.backend,
            probe_every=config.probe_every_steps,
        )
        self.spikes = SpikeRecord(config.params.dt_ms)
        self._probe_steps: list[np.ndarray] = []
        self._probe_v: list[np.ndarray] = []
        self.wall_running_s = 0.0
        self._recent: collections.deque = collections.deque(maxlen=20)  # (sim_ms, wall_s)
        self.set_probes(config.probe_root_ids, log_action=False)
        for spec in config.stimuli:
            self.add_stimulus(spec, log_action=False)
        for spec in config.interventions:
            self.add_intervention(spec, log_action=False)

    # ------------------------------------------------------------------ helpers
    @property
    def t_ms(self) -> float:
        return self.engine.t_ms

    def _log(self, action: str, **payload) -> None:
        self.actions.append({"t_ms": self.t_ms, "wall": utc_now(), "action": action, **payload})

    def _targets(self, sel: NeuronSelector) -> list[int]:
        idx = resolve(self.store, sel)
        local = self.network.local_of[idx]
        idx = idx[local >= 0]
        if len(idx) == 0:
            raise ValueError("selection matched no neurons inside the simulated network")
        return idx.tolist()

    # ------------------------------------------------------- stimuli/interventions
    def add_stimulus(
        self, spec: StimulusSpec, log_action: bool = True, relative: bool = False
    ) -> str:
        with self._lock:
            offset = self.t_ms if relative else 0.0
            stim = spec.to_stimulus(self._targets(spec.selector), offset_ms=offset)
            self.engine.add_stimulus(stim)
            self.stimulus_specs[stim.id] = spec
            if log_action:
                self._log(
                    "add_stimulus",
                    id=stim.id,
                    spec=spec.model_dump(),
                    relative=relative,
                    n_targets=len(stim.targets),
                )
            return stim.id

    def remove_stimulus(self, stim_id: str) -> bool:
        with self._lock:
            ok = self.engine.remove_stimulus(stim_id)
            self.stimulus_specs.pop(stim_id, None)
            if ok:
                self._log("remove_stimulus", id=stim_id)
            return ok

    def add_intervention(self, spec: InterventionSpec, log_action: bool = True) -> str:
        with self._lock:
            post = self._targets(spec.post_selector) if spec.post_selector else None
            item = spec.to_intervention(self._targets(spec.selector), post)
            self.engine.add_intervention(item)
            self.intervention_specs[item.id] = spec
            if log_action:
                self._log("add_intervention", id=item.id, spec=spec.model_dump())
            return item.id

    def remove_intervention(self, item_id: str) -> bool:
        with self._lock:
            ok = self.engine.remove_intervention(item_id)
            self.intervention_specs.pop(item_id, None)
            if ok:
                self._log("remove_intervention", id=item_id)
            return ok

    def clear_interventions(self) -> None:
        """Restore the unmodified connectome."""
        with self._lock:
            self.engine.set_interventions([])
            self.intervention_specs.clear()
            self._log("clear_interventions")

    def set_probes(self, root_ids: list[int], log_action: bool = True) -> list[int]:
        with self._lock:
            if len(root_ids) > 64:
                raise ValueError("at most 64 probes")
            idx = self.store.root_to_idx(root_ids, strict=True) if root_ids else np.zeros(0, int)
            local = self.network.local_of[idx]
            if (local < 0).any():
                raise ValueError("probe neurons must be inside the simulated network")
            self.engine.probe_local = local.astype(np.int64)
            self.probe_idx = idx.astype(np.int64)
            self._probe_steps.clear()
            self._probe_v.clear()
            if log_action:
                self._log("set_probes", root_ids=[int(r) for r in root_ids])
            return [int(r) for r in root_ids]

    def set_speed(self, speed: float | None) -> None:
        with self._lock:
            self.config.speed = speed
            self._log("set_speed", speed=speed)

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        with self._lock:
            if self.status in ("running",):
                return
            if self.status in ("finished", "error", "stopped"):
                raise RuntimeError(f"cannot start a {self.status} session; reset it first")
            self.status = "running"
            self._stop_flag = False
            self._log("start")
            self._ensure_thread()
            self._wake.set()

    def pause(self) -> None:
        with self._lock:
            if self.status == "running":
                self.status = "paused"
                self._log("pause")

    def resume(self) -> None:
        with self._lock:
            if self.status == "paused":
                self.status = "running"
                self._log("resume")
                self._ensure_thread()
                self._wake.set()

    def _ensure_thread(self) -> None:
        # a session paused by single-stepping has no worker thread yet
        if self._thread is None or not self._thread.is_alive():
            self._stop_flag = False
            self._thread = threading.Thread(target=self._loop, name=f"sim-{self.id}", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if self.status in ("running", "paused", "ready"):
                self.status = "stopped"
                self._log("stop")
            self._stop_flag = True
            self._wake.set()

    def reset(self, seed: int | None = None) -> None:
        self.stop()
        if self._thread is not None:
            self._thread.join(timeout=10)
        with self._lock:
            self.engine.reset(seed)
            if seed is not None:
                self.config.seed = int(seed)
            self.spikes.clear()
            self._probe_steps.clear()
            self._probe_v.clear()
            self.wall_running_s = 0.0
            self._recent.clear()
            self.status = "ready"
            self.error = None
            self._thread = None
            self._log("reset", seed=self.config.seed)

    def step(self, n_steps: int = 1) -> dict:
        """Advance synchronously while not running (single-step / small advances)."""
        if n_steps < 1 or n_steps > 100_000:
            raise ValueError("n_steps must be in [1, 100000]")
        with self._lock:
            if self.status == "running":
                raise RuntimeError("pause the session before stepping")
            if self.status in ("finished", "stopped", "error"):
                raise RuntimeError(f"session is {self.status}")
            self._log("step", n_steps=n_steps)
            frame = self._advance(n_steps)
            if self.status == "ready":
                self.status = "paused"
            return frame

    # --------------------------------------------------------------- execution
    def advance_external(self, n_steps: int, extra_events: tuple | None = None):
        """Advance under an external driver (the virtual-fly loop); returns the chunk result."""
        with self._lock:
            if self.status in ("finished", "stopped", "error"):
                raise RuntimeError(f"session is {self.status}")
            self.status = "external"
            self._advance(n_steps, extra_events, emit=False)
            return self._last_result

    def _advance(self, n_steps: int, extra_events: tuple | None = None, emit: bool = True) -> dict:
        p = self.config.params
        t_wall = time.perf_counter()
        res = self.engine.run(n_steps, extra_events)
        self._last_result = res
        wall = time.perf_counter() - t_wall
        self.wall_running_s += wall
        gidx = self.network.global_idx[res.spike_local]
        self.spikes.append(res.spike_steps, gidx)
        if len(res.probe_steps):
            self._probe_steps.append(res.probe_steps)
            self._probe_v.append(res.probe_v.astype(np.float32))
        self._recent.append((n_steps * p.dt_ms, wall))
        frame = {
            "type": "frame",
            "t_ms": self.t_ms,
            "chunk_ms": n_steps * p.dt_ms,
            "wall_running_s": self.wall_running_s,
            "sim_wall_ratio": self.sim_wall_ratio(),
            "n_spikes_total": len(self.spikes),
            "spike_t_ms": (res.spike_steps * p.dt_ms).tolist(),
            "spike_idx": gidx.tolist(),
            "probe_t_ms": (res.probe_steps * p.dt_ms).tolist(),
            "probe_v": res.probe_v.T.tolist(),
            "status": self.status,
        }
        if emit:
            for q in list(self._subscribers):
                q.append(frame)
        if self.t_ms >= self.config.max_duration_ms - 1e-9:
            self.status = "finished"
            self._log("finished")
        return frame

    def _loop(self) -> None:
        chunk = max(1, int(round(self.config.chunk_ms / self.config.params.dt_ms)))
        try:
            while True:
                with self._lock:
                    if self._stop_flag or self.status in ("stopped", "finished", "error"):
                        break
                    running = self.status == "running"
                if not running:
                    self._wake.wait(0.1)
                    self._wake.clear()
                    continue
                with self._lock:
                    remaining = int(
                        round((self.config.max_duration_ms - self.t_ms) / self.config.params.dt_ms)
                    )
                    n = max(1, min(chunk, remaining))
                    t0 = time.perf_counter()
                    self._advance(n)
                    speed = self.config.speed
                self._lock.yield_to_waiters()
                if speed:
                    target = n * self.config.params.dt_ms / 1000.0 / speed
                    sleep = target - (time.perf_counter() - t0)
                    if sleep > 0:
                        time.sleep(sleep)
        except Exception as exc:  # pragma: no cover - surfaced through status
            log.exception("simulation session failed", extra={"session": self.id})
            with self._lock:
                self.status = "error"
                self.error = f"{type(exc).__name__}: {exc}"
        finally:
            for q in list(self._subscribers):
                q.append({"type": "status", "status": self.status, "t_ms": self.t_ms})

    # ----------------------------------------------------------------- queries
    def sim_wall_ratio(self) -> float | None:
        sim = sum(s for s, _ in self._recent)
        wall = sum(w for _, w in self._recent)
        return (sim / 1000.0) / wall if wall > 0 else None

    def subscribe(self, maxlen: int = 256) -> collections.deque:
        q: collections.deque = collections.deque(maxlen=maxlen)  # drops oldest = backpressure
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: collections.deque) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def probe_traces(self) -> tuple[np.ndarray, np.ndarray]:
        with self._lock:
            if not self._probe_steps:
                return np.zeros(0), np.zeros((0, len(self.probe_idx)), dtype=np.float32)
            steps = np.concatenate(self._probe_steps)
            v = np.concatenate(self._probe_v)
            self._probe_steps, self._probe_v = [steps], [v]
            return steps * self.config.params.dt_ms, v

    def activity(self, t0_ms: float, t1_ms: float, top: int = 50) -> dict:
        n = len(self.root_ids)
        counts = self.spikes.counts(n, t0_ms, t1_ms)
        dur = max(t1_ms - t0_ms, 1e-9)
        active = np.nonzero(counts)[0]
        order = active[np.argsort(-counts[active])]
        nb = self.store.neurons
        region_col = (
            nb["primary_neuropil"] if nb["primary_neuropil"].notna().any() else (nb["super_class"])
        )
        return {
            "t0_ms": t0_ms,
            "t1_ms": t1_ms,
            "idx": active.tolist(),
            "rate_hz": (counts[active] / dur * 1000.0).tolist(),
            "top": [
                {
                    "idx": int(i),
                    "root_id": int(self.root_ids[i]),
                    "cell_type": _clean(nb.at[i, "cell_type"]),
                    "rate_hz": float(counts[i] / dur * 1000.0),
                }
                for i in order[:top]
            ],
            "regions": grouped_activity(counts, region_col, dur),
            "n_active": len(active),
        }

    def summary(self) -> dict:
        p = self.config.params
        return {
            "id": self.id,
            "label": self.config.label,
            "dataset_id": self.config.dataset_id,
            "synthetic": self.store.manifest.synthetic,
            "mode": self.network.mode,
            "n_neurons": self.network.n,
            "n_edges": self.network.graph.n_edges,
            "status": self.status,
            "error": self.error,
            "t_ms": self.t_ms,
            "max_duration_ms": self.config.max_duration_ms,
            "dt_ms": p.dt_ms,
            "seed": self.config.seed,
            "backend": self.config.backend,
            "speed": self.config.speed,
            "wall_running_s": self.wall_running_s,
            "sim_wall_ratio": self.sim_wall_ratio(),
            "n_spikes": len(self.spikes),
            "probe_root_ids": [int(self.root_ids[i]) for i in self.probe_idx],
            "stimuli": [{"id": k, **v.model_dump()} for k, v in self.stimulus_specs.items()],
            "interventions": [
                {"id": k, **v.model_dump()} for k, v in self.intervention_specs.items()
            ],
            "created_at": self.created_at,
            "evidence": "demonstration" if self.store.manifest.synthetic else "simulation_output",
        }

    def spikes_frame(self) -> pd.DataFrame:
        return self.spikes.to_frame(self.root_ids)


def _clean(v: object) -> str | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return str(v)


class SessionManager:
    """Bounded registry of live sessions (protects memory/CPU)."""

    def __init__(self, max_sessions: int = 4):
        self.max_sessions = max_sessions
        self._sessions: dict[str, SimulationSession] = {}
        self._lock = threading.Lock()

    def create(self, config: SessionConfig) -> SimulationSession:
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                # evict the oldest non-running session
                for sid, s in list(self._sessions.items()):
                    if s.status != "running":
                        s.stop()
                        del self._sessions[sid]
                        break
                else:
                    raise RuntimeError(f"too many running sessions (max {self.max_sessions})")
        session = SimulationSession(config)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, sid: str) -> SimulationSession:
        try:
            return self._sessions[sid]
        except KeyError:
            raise KeyError(f"no simulation session {sid}") from None

    def list(self) -> list[SimulationSession]:
        return list(self._sessions.values())

    def delete(self, sid: str) -> None:
        with self._lock:
            s = self._sessions.pop(sid, None)
        if s is not None:
            s.stop()

    def shutdown(self) -> None:
        for s in self.list():
            s.stop()
