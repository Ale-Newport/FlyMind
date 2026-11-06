"""Engine equivalence: FlyMind's Numba kernel vs a Brian2 build of the reference model.

Both receive identical external input events (pre-generated, seeded). Brian2 runs the
reference equations with method='linear' (exact integration) at dt = 0.1 ms; the FlyMind
kernel uses the same exact propagators, so spike trains are required to be identical and
membrane potentials equal to within floating-point rounding (1e-9 mV).
"""

import numpy as np
import pytest

from flymind.brain.brian2_engine import run_brian2
from flymind.brain.engine import BrainNetwork, LIFEngine
from flymind.brain.stimulus import CurrentStimulus, PoissonStimulus, Silencing, SynapticScaling

pytestmark = pytest.mark.brian2


def _compare(engine, n_steps):
    r = engine.run(n_steps)
    b = run_brian2(engine, n_steps, codegen="numpy")
    assert len(r.spike_steps) == len(b.spike_steps), (len(r.spike_steps), len(b.spike_steps))
    assert np.array_equal(r.spike_steps, b.spike_steps)
    assert np.array_equal(r.spike_local, b.spike_local)
    if len(engine.probe_local):
        np.testing.assert_allclose(r.probe_v, b.probe_v, atol=1e-9)
    return r


def test_identical_spikes_poisson_drive(store, group):
    eng = LIFEngine(
        BrainNetwork.full(store.graph),
        seed=11,
        probe_local=np.concatenate([group("chain_b"), group("pn_attr_l")[:3]]),
    )
    eng.add_stimulus(PoissonStimulus(targets=group("chain_a").tolist(), rate_hz=80))
    eng.add_stimulus(PoissonStimulus(targets=group("orn_attr_l").tolist(), rate_hz=150))
    r = _compare(eng, 2000)
    assert len(r.spike_steps) > 200


def test_identical_spikes_with_current_silencing_and_scaling(store, group):
    eng = LIFEngine(BrainNetwork.full(store.graph), seed=5, probe_local=group("vpn_r")[:4])
    eng.add_stimulus(
        PoissonStimulus(targets=group("orn_attr_r").tolist(), rate_hz=120, start_ms=20, stop_ms=150)
    )
    eng.add_stimulus(
        CurrentStimulus(targets=group("vis_r").tolist(), amplitude_mV=9, start_ms=10, stop_ms=120)
    )
    eng.add_intervention(Silencing(targets=group("ln_r").tolist(), mode="block_output"))
    eng.add_intervention(SynapticScaling(pre=group("pn_attr_r").tolist(), factor=0.5))
    _compare(eng, 2000)


def test_subnetwork_mode_equivalence(store, group):
    nodes = np.concatenate(
        [group(g) for g in ("orn_attr_l", "pn_attr_l", "lhn_attr_l", "dn_turn_l")]
    )
    eng = LIFEngine(BrainNetwork.subset(store.graph, nodes), seed=2)
    eng.add_stimulus(PoissonStimulus(targets=group("orn_attr_l").tolist(), rate_hz=150))
    _compare(eng, 1500)
