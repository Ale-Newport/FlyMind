"""Time-stepping kernels for the LIF network.

Two implementations with identical semantics:

* :func:`advance_numba` - compiled with Numba (default backend; releases the GIL).
* :func:`advance_numpy` - per-step NumPy vectorisation; slower, kept as an
  independent reference for testing the compiled kernel.

Per-step operation order mirrors Brian2's default schedule, which the reference
model (Shiu et al. 2024) runs on:

1. ``groups``: exact integration of (v, g) for non-refractory neurons
   (refractory neurons are frozen when ``hold_g`` is set, as in the reference
   "(unless refractory)" equations; otherwise only v is frozen).
2. ``thresholds``: spike if v > v_th and not refractory and not clamped.
3. ``synapses``: deliver presynaptic spikes emitted ``delay`` steps ago
   (g_post += w) and external input events for this step (added to v when
   ``ext_to_v``, as the reference model's PoissonInput(target_var='v') does).
4. ``resets``: v := v_reset (and g := 0 when ``reset_g``, as the reference
   reset ``v = v_rst; g = 0 mV``) for neurons that spiked this step.

Refractoriness follows Brian2: neuron i is refractory at step t while
``t - last_spike[i] < ref_steps[i]`` (per neuron, because the reference model sets
the refractory period of Poisson-stimulated neurons to zero), and also during the
step in which it spikes. Brian2 turns the "(unless refractory)" flag into a
*conditional write* on every code object except the thresholder/resetter, so
synaptic (``g += w``) and Poisson (``v += w``) input that arrives while the target is
refractory is discarded, not accumulated (``drop_refr``; verified against Brian2
2.11 in tests/unit/test_brian2_equivalence.py).
"""

from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True, nogil=True)
def advance_numba(
    n_steps,
    t0,
    v,
    g,
    last_spike,
    drive,
    clamped,
    indptr,
    indices,
    weights,
    ring,
    ring_count,
    delay_steps,
    ext_steps,
    ext_idx,
    ext_w,
    ext_to_v,
    a_vv,
    a_vg,
    a_gg,
    v_rest,
    v_reset,
    v_th,
    ref_steps,
    hold_g,
    reset_g,
    drop_refr,
    out_steps,
    out_idx,
    probe_idx,
    probe_every,
    probe_v,
    probe_g,
):  # pragma: no cover - compiled
    n = v.shape[0]
    n_ring = ring.shape[0]
    n_out = 0
    n_ext = ext_steps.shape[0]
    e = 0
    n_probe_rows = 0
    spiked = np.empty(n, dtype=np.int64)
    for s in range(n_steps):
        t = t0 + s
        if out_steps.shape[0] - n_out < n:
            return s, n_out, n_probe_rows, True  # caller grows buffers and resumes at step s
        # 1. integrate
        for i in range(n):
            if t - last_spike[i] >= ref_steps[i]:
                e_i = v_rest + drive[i]
                v[i] = e_i + (v[i] - e_i) * a_vv + g[i] * a_vg
                g[i] = g[i] * a_gg
            elif not hold_g:
                g[i] = g[i] * a_gg
        # 2. threshold
        n_sp = 0
        for i in range(n):
            if v[i] > v_th and t - last_spike[i] >= ref_steps[i] and not clamped[i]:
                spiked[n_sp] = i
                n_sp += 1
                last_spike[i] = t
        slot_w = t % n_ring
        for k in range(n_sp):
            ring[slot_w, k] = spiked[k]
        ring_count[slot_w] = n_sp
        # 3. synapses: deliver spikes emitted at t - delay
        if t - delay_steps >= 0 or delay_steps == 0:
            slot_r = (t - delay_steps) % n_ring
            for k in range(ring_count[slot_r]):
                j = ring[slot_r, k]
                for q in range(indptr[j], indptr[j + 1]):
                    tgt = indices[q]
                    if drop_refr and (last_spike[tgt] == t or t - last_spike[tgt] < ref_steps[tgt]):
                        continue
                    g[tgt] += weights[q]
        while e < n_ext and ext_steps[e] < t:
            e += 1
        while e < n_ext and ext_steps[e] == t:
            tgt = ext_idx[e]
            if not (drop_refr and (last_spike[tgt] == t or t - last_spike[tgt] < ref_steps[tgt])):
                if ext_to_v:
                    v[tgt] += ext_w[e]
                else:
                    g[tgt] += ext_w[e]
            e += 1
        # 4. reset
        for k in range(n_sp):
            v[spiked[k]] = v_reset
            if reset_g:
                g[spiked[k]] = 0.0
        # clamped neurons are held at rest (Kir2.1-like silencing)
        for i in range(n):
            if clamped[i]:
                v[i] = v_rest
        # record
        for k in range(n_sp):
            out_steps[n_out] = t
            out_idx[n_out] = spiked[k]
            n_out += 1
        if probe_idx.shape[0] > 0 and (t % probe_every) == 0:
            for p in range(probe_idx.shape[0]):
                probe_v[n_probe_rows, p] = v[probe_idx[p]]
                probe_g[n_probe_rows, p] = g[probe_idx[p]]
            n_probe_rows += 1
    return n_steps, n_out, n_probe_rows, False


def advance_numpy(
    n_steps,
    t0,
    v,
    g,
    last_spike,
    drive,
    clamped,
    indptr,
    indices,
    weights,
    ring,
    ring_count,
    delay_steps,
    ext_steps,
    ext_idx,
    ext_w,
    ext_to_v,
    a_vv,
    a_vg,
    a_gg,
    v_rest,
    v_reset,
    v_th,
    ref_steps,
    hold_g,
    reset_g,
    drop_refr,
    out_steps,
    out_idx,
    probe_idx,
    probe_every,
    probe_v,
    probe_g,
):
    """Reference implementation (same signature/semantics as :func:`advance_numba`)."""
    n_ring = ring.shape[0]
    n_out = 0
    n_probe_rows = 0
    e_rest = v_rest + drive
    pre_of_edge = np.repeat(np.arange(len(indptr) - 1), np.diff(indptr))
    n = len(v)
    for s in range(n_steps):
        t = t0 + s
        if len(out_steps) - n_out < n:
            return s, n_out, n_probe_rows, True
        active = (t - last_spike) >= ref_steps
        v_new = e_rest + (v - e_rest) * a_vv + g * a_vg
        v[:] = np.where(active, v_new, v)
        decay = active if hold_g else np.ones_like(active)
        g[:] = np.where(decay, g * a_gg, g)
        spk = np.nonzero((v > v_th) & active & ~clamped)[0]
        last_spike[spk] = t
        slot_w = t % n_ring
        ring[slot_w, : len(spk)] = spk
        ring_count[slot_w] = len(spk)
        receptive = (
            ~((last_spike == t) | (t - last_spike < ref_steps))
            if drop_refr
            else (np.ones(len(v), dtype=bool))
        )
        if t - delay_steps >= 0 or delay_steps == 0:
            slot_r = (t - delay_steps) % n_ring
            src = ring[slot_r, : ring_count[slot_r]]
            if len(src):
                mask = np.isin(pre_of_edge, src) & receptive[indices]
                np.add.at(g, indices[mask], weights[mask])
        sel = (ext_steps == t) & receptive[ext_idx] if len(ext_idx) else ext_steps == t
        if sel.any():
            np.add.at(v if ext_to_v else g, ext_idx[sel], ext_w[sel])
        v[spk] = v_reset
        if reset_g:
            g[spk] = 0.0
        v[clamped] = v_rest
        out_steps[n_out : n_out + len(spk)] = t
        out_idx[n_out : n_out + len(spk)] = spk
        n_out += len(spk)
        if len(probe_idx) and t % probe_every == 0:
            probe_v[n_probe_rows] = v[probe_idx]
            probe_g[n_probe_rows] = g[probe_idx]
            n_probe_rows += 1
    return n_steps, n_out, n_probe_rows, False
