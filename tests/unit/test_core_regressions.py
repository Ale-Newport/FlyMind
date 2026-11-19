"""Regression tests for simulation, data and streaming bugs found in the 0.2.x audit."""

from typing import ClassVar

import numpy as np
import pytest
from pydantic import ValidationError

from flymind.brain.engine import BrainNetwork, LIFEngine
from flymind.brain.stimulus import CurrentStimulus, PoissonStimulus
from flymind.connectome.graph import SparseGraph


def _single_neuron() -> BrainNetwork:
    z = np.zeros(0, dtype=np.int64)
    return BrainNetwork.full(SparseGraph.from_edges(1, z, z, np.zeros(0), np.zeros(0)))


def _first_rise(window: tuple[float, float], chunks: list[int]) -> tuple[int, int]:
    """(first, last) step at which a 5 mV current window depolarises the neuron."""
    eng = LIFEngine(_single_neuron(), seed=0, probe_local=np.array([0]))
    eng.add_stimulus(
        CurrentStimulus(targets=[0], amplitude_mV=5, start_ms=window[0], stop_ms=window[1])
    )
    v = np.concatenate([eng.run(n).probe_v[:, 0] for n in chunks])
    rising = np.nonzero(np.diff(v) > 1e-9)[0] + 1
    return int(rising[0]), int(rising[-1])


@pytest.mark.parametrize("window", [(3.3 + 1.0, 9.3), (1.0, 6.05)])
def test_current_window_is_decided_in_steps_and_chunk_independent(window):
    """Edges just off the dt grid (3.3 + 1.0 = 4.300000000000001) used to switch the drive
    off for a whole segment, or leave it on until the end of the chunk."""
    one = _first_rise(window, [300])
    many = _first_rise(window, [10] * 30)
    assert one == many
    start, stop = round(window[0] / 0.1), round(window[1] / 0.1)
    assert one[0] == start  # the probe sample of the first driven step already rises
    assert one[1] <= stop


def test_invalid_stimulus_timing_is_rejected_up_front():
    from flymind.brain.session import StimulusSpec
    from flymind.connectome.selectors import NeuronSelector

    sel = NeuronSelector(group="chain_a")
    for bad in (
        {"repeats": 3, "interval_ms": 0, "stop_ms": 50},  # the Simulator form's defaults
        {"repeats": 2, "interval_ms": 100},  # open-ended window cannot repeat
        {"repeats": 2, "interval_ms": 10, "start_ms": 0, "stop_ms": 50},  # overlapping
        {"start_ms": 20, "stop_ms": 10},
    ):
        with pytest.raises(ValidationError):
            StimulusSpec(selector=sel, **bad)
        with pytest.raises(ValidationError):
            PoissonStimulus(targets=[0], **bad)
    ok = StimulusSpec(selector=sel, start_ms=50, stop_ms=150, repeats=5, interval_ms=300)
    assert ok.repeats == 5


def test_binned_counts_are_half_open_and_complete():
    from flymind.brain.recording import binned_counts, population_rate

    steps = np.arange(0, 160, 10)  # one neuron at 1000 Hz on a 0.1 ms grid
    idx = np.zeros_like(steps)
    t, r = population_rate(steps, idx, np.array([0]), 0.0, 15.0, 10.0, 0.1)
    assert t.tolist() == [5.0] and r.tolist() == [1000.0]  # the spike at 10 ms is in bin 2
    t, r = population_rate(steps, idx, np.array([0]), 0.0, 16.0, 10.0, 0.1)
    assert r.tolist() == [1000.0]  # no partial trailing bin
    _, counts = binned_counts(np.array([0.0, 9.999999999999998, 10.0]), 0, 20, 10)
    assert counts.tolist() == [1, 2]


def test_region_activity_counts_only_simulated_neurons():
    import pandas as pd

    from flymind.brain.recording import grouped_activity

    counts = np.array([10, 0, 0, 0])
    labels = pd.Series(["A", "A", "A", "B"])
    (row,) = grouped_activity(counts, labels, 1000.0)
    assert row["neurons"] == 3 and row["mean_rate_hz"] == pytest.approx(10 / 3)
    (row,) = grouped_activity(counts, labels, 1000.0, simulated=np.array([0, 3]))
    assert row["neurons"] == 1 and row["mean_rate_hz"] == pytest.approx(10.0)


def test_session_regions_use_the_simulated_circuit(store):
    from flymind.brain.session import SessionConfig, SimulationSession

    cfg = SessionConfig(
        dataset_id="synthetic_demo_v1",
        network={"mode": "circuit", "selection": {"group": "orn_attr_l"}, "expand_depth": 1},
        stimuli=[{"selector": {"group": "orn_attr_l"}, "rate_hz": 200}],
    )
    s = SimulationSession(cfg)
    try:
        s.step(500)
        simulated = set(s.network.global_idx.tolist())
        labels = store.neurons["primary_neuropil"].fillna("unassigned")
        for reg in s.activity(0, s.t_ms)["regions"]:
            in_region = labels[labels == reg["label"]].index
            assert reg["neurons"] == len(simulated.intersection(in_region))
    finally:
        s.stop()


def test_stream_merge_takes_metadata_from_frames_not_status():
    from flymind.api.routes_sim import _merge

    def frame(t, spikes, probes):
        return {
            "type": "frame",
            "t_ms": t,
            "status": "running",
            "sim_wall_ratio": 0.5,
            "wall_running_s": t / 500,
            "n_spikes_total": 10 * t,
            "spike_t_ms": spikes,
            "spike_idx": list(range(len(spikes))),
            "probe_t_ms": [t],
            "probe_v": [[-52.0]] * probes,
        }

    status = {"type": "status", "status": "finished", "t_ms": 20}
    m = _merge([frame(10, [1.0, 2.0], 1), frame(20, [11.0, 12.0], 1), status], 20_000)
    assert m["n_spikes_total"] == 200 and m["sim_wall_ratio"] == 0.5
    assert m["status"] == "finished" and m["spike_t_ms"] == [1.0, 2.0, 11.0, 12.0]
    assert m["probe_t_ms"] == [10, 20] and m["probe_v"] == [[-52.0, -52.0]]
    assert _merge([frame(10, [1.0], 0)], 0)["spike_t_ms"] == []  # max_spikes=0 sends none
    assert _merge([status], 100) is None
    changed = _merge([frame(10, [], 1), frame(20, [], 2)], 100)  # a probe was added
    assert changed["probe_t_ms"] == [20] and len(changed["probe_v"]) == 2


def test_flight_step_keeps_body_and_brain_clocks_together():
    from flymind.embodiment.body import FlyBody

    class Stub:
        t_s = 0.0
        _vision_age = 0.0

        class flight:
            calls: ClassVar[list[float]] = []

            @classmethod
            def step(cls, cmd, dt):
                cls.calls.append(dt)

        def _sync_flight_pose(self):
            pass

    for interval_ms in (0.5, 1.0, 1.4, 2.0):
        body = Stub()
        Stub.flight.calls = []
        FlyBody.fly_step(body, None, interval_ms / 1000)
        assert body.t_s == pytest.approx(interval_ms / 1000)
        assert body._vision_age == pytest.approx(interval_ms / 1000)  # vision keeps refreshing
        assert sum(Stub.flight.calls) == pytest.approx(interval_ms / 1000)
        assert max(Stub.flight.calls) <= 1e-3 + 1e-12
