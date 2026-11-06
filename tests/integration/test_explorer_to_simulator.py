"""Selecting a neuron (by root ID, as the explorer does) and stimulating it produces the
expected downstream events in a known test circuit."""

import numpy as np

from flymind.brain.params import LIFParams
from flymind.brain.session import NetworkConfig, SessionConfig, SimulationSession, StimulusSpec
from flymind.connectome.selectors import NeuronSelector


def test_selected_neuron_drives_downstream_chain(store, group):
    a, b, c = (int(store.idx_to_root(group(g))[0]) for g in ("chain_a", "chain_b", "chain_c"))
    s = SimulationSession(
        SessionConfig(
            dataset_id="synthetic_demo_v1", network=NetworkConfig(mode="demo"), max_duration_ms=200
        )
    )
    s.add_stimulus(
        StimulusSpec(
            selector=NeuronSelector(root_ids=[a]),
            kind="pulse_train",
            frequency_hz=1,
            start_ms=0,
            stop_ms=1,
        )
    )
    s.step(2000)
    df = s.spikes_frame()
    t = {rid: df.loc[df.root_id == rid, "step"].to_numpy() for rid in (a, b, c)}
    assert len(t[a]) == 1 and len(t[b]) == 1 and len(t[c]) == 1
    p = LIFParams()
    w = 200 * p.w_syn_mV  # fixture chain: 200 synapses per hop
    k = np.arange(1, 400)
    u = (
        w
        * p.tau_syn_ms
        / (p.tau_syn_ms - p.tau_m_ms)
        * (np.exp(-k * p.dt_ms / p.tau_syn_ms) - np.exp(-k * p.dt_ms / p.tau_m_ms))
    )
    k_star = int(k[np.argmax(u > p.v_threshold_mV - p.v_rest_mV)])  # analytic PSP crossing
    # each hop = synaptic delay + exact time for the PSP to cross threshold
    assert t[b][0] == t[a][0] + p.delay_steps + k_star
    assert t[c][0] == t[b][0] + p.delay_steps + k_star
    # the action log records what was done, at which simulated time
    assert [x["action"] for x in s.actions] == ["add_stimulus", "step", "finished"]
    assert s.actions[1]["t_ms"] == 0.0 and s.t_ms == 200.0
