import numpy as np
import pandas as pd
import pytest

from flymind.connectome.adapters.flywire import _ids
from flymind.connectome.graph import GraphQueries, SparseGraph
from flymind.connectome.validate import float_corruption_suspected

BIG = 720575940629970489  # > 2**53: not representable as float64


def test_float64_would_corrupt_flywire_ids():
    assert int(float(BIG)) != BIG


def test_id_parser_keeps_exact_int64_and_rejects_floats():
    out = _ids(pd.Series([str(BIG), "720575940621014292"]))
    assert out.dtype == np.int64 and out[0] == BIG
    with pytest.raises(ValueError):
        _ids(pd.Series(["7.205759406299705e+17"]))
    with pytest.raises(ValueError):
        _ids(pd.Series([str(BIG), None]))


def test_float_corruption_detector():
    rng = np.random.default_rng(0)
    exact = 720575940600000000 + rng.integers(0, 10**10, 1000)
    rounded = np.array([int(float(x)) for x in exact], dtype=np.int64)
    assert not float_corruption_suspected(exact)
    assert float_corruption_suspected(rounded)


def _graph():
    # 0->1 (5), 0->2 (2), 1->2 (7), 2->3 (9), 3->0 (1)
    return SparseGraph.from_edges(
        4,
        np.array([1, 0, 2, 0, 3]),
        np.array([2, 1, 3, 2, 0]),
        np.array([7, 5, 9, 2, 1]),
        np.array([1, 1, -1, 1, 1]),
    )


def test_csr_sorted_and_directed():
    g = _graph()
    assert g.n_edges == 5 and g.n_synapses == 24
    assert g.indptr.tolist() == [0, 2, 3, 4, 5]
    post, cnt, _sgn = g.downstream(0)
    assert post.tolist() == [1, 2] and cnt.tolist() == [5, 2]
    q = GraphQueries(g)
    pre, cnt, _sgn = q.upstream(2)
    assert sorted(zip(pre.tolist(), cnt.tolist(), strict=True)) == [(0, 2), (1, 7)]
    assert q.upstream(3)[2].tolist() == [-1]  # edge sign belongs to the presynaptic neuron


def test_duplicate_edges_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        SparseGraph.from_edges(
            2, np.array([0, 0]), np.array([1, 1]), np.array([1, 2]), np.array([1, 1])
        )


def test_subgraph_neighbourhood_and_paths():
    g = _graph()
    sub, nodes = g.subgraph(np.array([0, 1, 2]))
    assert nodes.tolist() == [0, 1, 2] and sub.n_edges == 3
    q = GraphQueries(g)
    assert q.neighborhood(np.array([0]), 1, "downstream", min_syn=1) == {0: 0, 1: 1, 2: 1}
    assert q.neighborhood(np.array([0]), 1, "downstream", min_syn=3) == {0: 0, 1: 1}
    assert q.shortest_path(np.array([0]), np.array([3]), min_syn=1) == [0, 2, 3]
    assert q.shortest_path(np.array([0]), np.array([3]), min_syn=3) == [0, 1, 2, 3]
    assert q.shortest_path(np.array([3]), np.array([1]), min_syn=10) is None
