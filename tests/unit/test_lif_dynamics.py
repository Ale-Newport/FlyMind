"""Analytical and semantic tests of the LIF engine (fast; no Brian2)."""

import math

import numpy as np
import pytest

from flymind.brain.engine import BrainNetwork, LIFEngine
from flymind.brain.params import LIFParams
from flymind.brain.stimulus import (
    CurrentStimulus,
    PoissonStimulus,
    PulseTrainStimulus,
    Silencing,
    SynapticScaling,
)
from flymind.connectome.graph import SparseGraph

P = LIFParams()


def net(edges, n):
    pre, post, cnt, sgn = (np.array(x) for x in zip(*edges, strict=True)) if edges else ([],) * 4
    return BrainNetwork.full(
        SparseGraph.from_edges(
            n,
            np.array(pre, dtype=np.int64),
            np.array(post, dtype=np.int64),
            np.array(cnt),
            np.array(sgn),
        )
    )


@pytest.mark.parametrize("backend", ["numba", "numpy"])
def test_constant_drive_threshold_time_matches_analytic(backend):
    drive = 10.0  # mV
    eng = LIFEngine(net([], 1), seed=0, backend=backend)
    eng.add_stimulus(CurrentStimulus(targets=[0], amplitude_mV=drive))
    res = eng.run(800)
    gap = P.v_threshold_mV - P.v_rest_mV
    t_star = -P.tau_m_ms * math.log(1 - gap / drive)  # 24.08 ms
    first = int(math.ceil(t_star / P.dt_ms)) - 1  # v after step t reflects t+1 updates
    assert res.spike_steps[0] == first
    # integration restarts refractory_steps after the spike and needs the same
    # first + 1 updates to reach threshold again: ISI = refractory_steps + first
    assert res.spike_steps[1] - res.spike_steps[0] == P.refractory_steps + first


def test_psp_shape_delay_and_sign():
    w_count = 20
    eng = LIFEngine(
        net([(0, 1, w_count, 1), (0, 2, w_count, -1)], 3), seed=0, probe_local=np.array([1, 2])
    )
    eng.add_stimulus(PulseTrainStimulus(targets=[0], frequency_hz=1, start_ms=0, stop_ms=1))
    res = eng.run(400)
    s0 = res.spike_steps[res.spike_local == 0][0]
    assert s0 == 1  # kick at step 0 (synapses slot) -> threshold crossing at step 1
    arrival = s0 + P.delay_steps
    w = w_count * P.w_syn_mV
    v1 = res.probe_v[:, 0]
    assert np.all(v1[: arrival + 1] == P.v_rest_mV)  # nothing before the delayed arrival
    k = np.arange(1, 300)
    expected = P.v_rest_mV + w * P.tau_syn_ms / (P.tau_syn_ms - P.tau_m_ms) * (
        np.exp(-k * P.dt_ms / P.tau_syn_ms) - np.exp(-k * P.dt_ms / P.tau_m_ms)
    )
    np.testing.assert_allclose(v1[arrival + k], expected, atol=1e-9)
    assert res.probe_v[arrival + 50, 1] < P.v_rest_mV  # inhibitory partner hyperpolarises


def test_reset_refractory_and_stimulated_neurons_have_no_refractory_period():
    eng = LIFEngine(net([], 2), seed=0, probe_local=np.array([0, 1]))
    eng.add_stimulus(CurrentStimulus(targets=[1], amplitude_mV=30))
    # neuron 0: 1 kHz pulses (1 ms apart < 2.2 ms refractory period) -> every pulse fires,
    # because the reference model sets t_ref = 0 for stimulated neurons
    eng.add_stimulus(PulseTrainStimulus(targets=[0], frequency_hz=1000, start_ms=0, stop_ms=10))
    res = eng.run(300)
    sp0 = res.spike_steps[res.spike_local == 0]
    assert len(sp0) == 10 and np.all(np.diff(sp0) == 10)
    sp1 = res.spike_steps[res.spike_local == 1]
    s = sp1[0]
    v = res.probe_v[:, 1]
    assert v[s] == P.v_reset_mV
    assert np.all(v[s : s + P.refractory_steps] == P.v_reset_mV)  # frozen while refractory
    assert v[s + P.refractory_steps] > P.v_reset_mV


def test_input_during_refractory_is_dropped_like_brian2():
    # neuron 1 is forced to spike by a strong current, then receives one synaptic event
    # while refractory: the event must have no effect (Brian2 conditional write).
    eng2 = LIFEngine(net([(0, 1, 100, 1)], 2), seed=0, probe_local=np.array([1]))
    eng2.add_stimulus(CurrentStimulus(targets=[1], amplitude_mV=100, start_ms=0, stop_ms=2.0))
    eng2.add_stimulus(PulseTrainStimulus(targets=[0], frequency_hz=1, start_ms=0, stop_ms=0.1))
    res = eng2.run(200)
    arrival = int(res.spike_steps[res.spike_local == 0][0]) + P.delay_steps
    last = int(res.spike_steps[res.spike_local == 1][-1])
    assert last < arrival < last + P.refractory_steps
    assert np.all(res.probe_v[arrival:, 0] <= P.v_reset_mV + 1e-12)  # event discarded


def test_seeded_determinism_and_chunk_independence(store, group):
    net_full = BrainNetwork.full(store.graph)
    tgt = group("orn_attr_l").tolist()

    def run(seed, chunks):
        e = LIFEngine(net_full, seed=seed)
        e.add_stimulus(PoissonStimulus(targets=tgt, rate_hz=150))
        out = [e.run(c) for c in chunks]
        return np.concatenate([o.spike_steps for o in out]), np.concatenate(
            [o.spike_local for o in out]
        )

    a = run(7, [3000])
    b = run(7, [1, 999, 1500, 500])
    c = run(8, [3000])
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
    assert not (len(a[0]) == len(c[0]) and np.array_equal(a[1], c[1]))


def test_numba_and_numpy_backends_identical(store, group):
    net_full = BrainNetwork.full(store.graph)
    outs = []
    for backend in ("numba", "numpy"):
        e = LIFEngine(net_full, seed=3, backend=backend, probe_local=np.arange(0, 1000, 97))
        e.add_stimulus(PoissonStimulus(targets=group("orn_attr_l").tolist(), rate_hz=150))
        e.add_stimulus(CurrentStimulus(targets=group("vis_r").tolist(), amplitude_mV=9))
        e.add_intervention(Silencing(targets=group("ln_l").tolist()))
        outs.append(e.run(1500))
    assert np.array_equal(outs[0].spike_steps, outs[1].spike_steps)
    assert np.array_equal(outs[0].spike_local, outs[1].spike_local)
    np.testing.assert_allclose(outs[0].probe_v, outs[1].probe_v, atol=1e-12)


def test_float32_precision_close_to_float64(store, group):
    net_full = BrainNetwork.full(store.graph)
    rates = []
    for prec in ("float64", "float32"):
        e = LIFEngine(net_full, LIFParams(precision=prec), seed=1)
        e.add_stimulus(PoissonStimulus(targets=group("grn_sugar").tolist(), rate_hz=150))
        r = e.run(10000)
        mn = group("mn_feed")
        rates.append(np.isin(r.spike_local, mn).sum())
    # identical inputs; float32 rounding may shift threshold crossings slightly
    assert abs(rates[0] - rates[1]) <= max(3, 0.05 * rates[0])


def test_silencing_and_reversible_lesions(store, group):
    A, B, C = (group(g).tolist() for g in ("chain_a", "chain_b", "chain_c"))
    net_full = BrainNetwork.full(store.graph)

    def counts(interventions):
        e = LIFEngine(net_full, seed=0)
        e.add_stimulus(PoissonStimulus(targets=A, rate_hz=100))
        e.set_interventions(interventions)
        r = e.run(5000)
        return [int(np.isin(r.spike_local, x).sum()) for x in (A, B, C)]

    intact = counts([])
    assert intact[1] > 0 and intact[2] > 0  # A -> B -> C propagates
    blocked = counts([Silencing(targets=B, mode="block_output")])
    assert blocked[1] == intact[1] and blocked[2] == 0  # TNT-like: B fires, output removed
    clamped = counts([Silencing(targets=B, mode="clamp")])
    assert clamped[1] == 0 and clamped[2] == 0
    lesion = counts([SynapticScaling(pre=A, post=B, factor=0.0)])
    assert lesion[1] == 0
    e = LIFEngine(net_full, seed=0)
    w0 = e.weights.copy()
    e.add_intervention(it := SynapticScaling(pre=A, factor=0.0))
    assert not np.array_equal(e.weights, w0)
    e.remove_intervention(it.id)
    assert np.array_equal(e.weights, w0)  # original connectome restored
    assert np.array_equal(net_full.graph.syn_count, store.graph.syn_count)  # never mutated


def test_inhibition_suppresses_target(store, group):
    A, C, inh = (group(g).tolist() for g in ("chain_a", "chain_c", "chain_i"))
    net_full = BrainNetwork.full(store.graph)
    out = []
    for with_inh in (False, True):
        e = LIFEngine(net_full, seed=0)
        e.add_stimulus(PoissonStimulus(targets=A, rate_hz=100))
        if with_inh:
            e.add_stimulus(PoissonStimulus(targets=inh, rate_hz=300))
        r = e.run(5000)
        out.append(int(np.isin(r.spike_local, C).sum()))
    assert out[1] < out[0] * 0.5


def test_repeated_stimulus_windows():
    s = PoissonStimulus(targets=[0], start_ms=10, stop_ms=20, repeats=3, interval_ms=50)
    assert s.windows() == [(10, 20), (60, 70), (110, 120)]
    with pytest.raises(ValueError):
        PoissonStimulus(targets=[0], start_ms=0, repeats=2, interval_ms=10).windows()
