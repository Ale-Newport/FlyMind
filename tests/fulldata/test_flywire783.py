"""Optional tests on the real FlyWire v783 dataset (skipped unless imported)."""

import numpy as np
import pytest

from flymind.brain.engine import BrainNetwork, LIFEngine
from flymind.brain.stimulus import PoissonStimulus
from flymind.connectome.selectors import NeuronSelector, resolve

pytestmark = pytest.mark.fulldata


def test_published_dataset_statistics(real_store):
    m = real_store.manifest
    assert m.n_neurons == 139_255
    assert m.n_edges == 15_091_983 and m.n_synapses == 54_492_922  # Shiu et al. v783 table
    assert m.validation_status == "passed"
    nb = real_store.neurons
    assert nb["root_id"].astype(str).str.startswith("720575940").all()


def test_sugar_grns_drive_mn9_on_v783(real_store):
    sugar = real_store.root_to_idx([int(r) for r in resolve_group(real_store, "sugar_grn_shiu")])
    mn9 = real_store.root_to_idx([720575940660219265])
    eng = LIFEngine(BrainNetwork.full(real_store.graph), seed=0)
    eng.add_stimulus(PoissonStimulus(targets=sugar.tolist(), rate_hz=150))
    r = eng.run(10_000)
    rate = np.isin(r.spike_local, mn9).sum() / 1.0
    assert rate > 50  # Shiu et al. report strong MN9 activation; kornel77777 asserts > 50 Hz
    active = len(np.unique(r.spike_local))
    assert 200 < active < 800


def resolve_group(store, name):
    return store.idx_to_root(resolve(store, NeuronSelector(group=name)))


def test_known_pathway_sugar_to_mn9(real_store):
    src = real_store.root_to_idx([720575940624963786])
    dst = real_store.root_to_idx([720575940660219265])
    path = real_store.queries.shortest_path(src, dst, min_syn=5, max_depth=4)
    assert path is not None and len(path) <= 5


def test_skeleton_geometry_if_installed(real_store, monkeypatch):
    from flymind.visualization import geometry

    monkeypatch.setenv("FLYMIND_DATA_DIR", str(real_store.directory.parents[1]))
    geometry.SkeletonStore._instance = None

    try:
        payload = geometry.skeleton_payload(720575940604737708, lod=1)  # DNa02 (right)
    except geometry.SkeletonUnavailableError:
        pytest.skip("skeletons not installed")
    assert payload["n_segments"] > 1000
    assert payload["simplification"]["kept_nodes"] <= payload["simplification"]["original_nodes"]
