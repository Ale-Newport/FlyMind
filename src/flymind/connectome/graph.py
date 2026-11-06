"""Sparse directed connectivity (CSR for outgoing, CSC for incoming edges).

The full FlyWire graph has ~15 million aggregated edges, so connectivity is held
as flat NumPy arrays (optionally memory-mapped) rather than Python objects.
Rows are presynaptic neurons, columns postsynaptic neurons.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.sparse as sp


@dataclass(frozen=True)
class SparseGraph:
    n: int
    indptr: np.ndarray  # int64, length n+1  (outgoing, CSR)
    indices: np.ndarray  # int32, postsynaptic idx
    syn_count: np.ndarray  # int32
    sign: np.ndarray  # int8 (+1/-1)

    # ------------------------------------------------------------------ build/io
    @classmethod
    def from_edges(
        cls, n: int, pre: np.ndarray, post: np.ndarray, syn_count: np.ndarray, sign: np.ndarray
    ) -> SparseGraph:
        """Build from (possibly unsorted) aggregated edges. Duplicates are rejected."""
        pre = np.asarray(pre, dtype=np.int64)
        post = np.asarray(post, dtype=np.int64)
        if len(pre) and (pre.min() < 0 or post.min() < 0 or pre.max() >= n or post.max() >= n):
            raise ValueError("edge endpoint outside [0, n)")
        order = np.lexsort((post, pre))
        pre, post = pre[order], post[order]
        syn_count = np.asarray(syn_count, dtype=np.int32)[order]
        sign = np.asarray(sign, dtype=np.int8)[order]
        if len(pre) > 1:
            dup = (pre[1:] == pre[:-1]) & (post[1:] == post[:-1])
            if dup.any():
                raise ValueError(f"{int(dup.sum())} duplicate (pre, post) edges; aggregate first")
        indptr = np.zeros(n + 1, dtype=np.int64)
        np.add.at(indptr, pre + 1, 1)
        np.cumsum(indptr, out=indptr)
        return cls(n, indptr, post.astype(np.int32), syn_count, sign)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "csr_indptr.npy", self.indptr)
        np.save(directory / "csr_indices.npy", self.indices)
        np.save(directory / "csr_syn_count.npy", self.syn_count)
        np.save(directory / "csr_sign.npy", self.sign)

    @classmethod
    def load(cls, directory: Path, mmap: bool = True) -> SparseGraph:
        mode = "r" if mmap else None
        indptr = np.load(directory / "csr_indptr.npy", mmap_mode=mode)
        return cls(
            n=len(indptr) - 1,
            indptr=indptr,
            indices=np.load(directory / "csr_indices.npy", mmap_mode=mode),
            syn_count=np.load(directory / "csr_syn_count.npy", mmap_mode=mode),
            sign=np.load(directory / "csr_sign.npy", mmap_mode=mode),
        )

    # ---------------------------------------------------------------- properties
    @property
    def n_edges(self) -> int:
        return len(self.indices)

    @property
    def n_synapses(self) -> int:
        return int(np.asarray(self.syn_count, dtype=np.int64).sum())

    def pre_indices(self) -> np.ndarray:
        """Presynaptic idx of every edge (expanded from indptr)."""
        return np.repeat(np.arange(self.n, dtype=np.int32), np.diff(self.indptr))

    def to_scipy(self, weights: np.ndarray | None = None) -> sp.csr_matrix:
        data = self.syn_count if weights is None else weights
        return sp.csr_matrix((data, self.indices, self.indptr), shape=(self.n, self.n))

    def transpose_index(self) -> CscIndex:
        """Incoming-edge index (CSC): for each post neuron, the CSR edge ids targeting it."""
        order = np.argsort(self.indices, kind="stable")
        counts = np.bincount(self.indices, minlength=self.n)
        indptr = np.zeros(self.n + 1, dtype=np.int64)
        np.cumsum(counts, out=indptr[1:])
        return CscIndex(
            indptr=indptr, edge_ids=order.astype(np.int64), pre=self.pre_indices()[order]
        )

    # ------------------------------------------------------------------- queries
    def out_edges(self, i: int) -> slice:
        return slice(int(self.indptr[i]), int(self.indptr[i + 1]))

    def downstream(self, i: int, min_syn: int = 1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        s = self.out_edges(i)
        post, cnt, sgn = self.indices[s], self.syn_count[s], self.sign[s]
        keep = cnt >= min_syn
        return np.asarray(post[keep]), np.asarray(cnt[keep]), np.asarray(sgn[keep])

    def subgraph(self, nodes: np.ndarray) -> tuple[SparseGraph, np.ndarray]:
        """Induced subgraph on ``nodes`` (global idx). Returns (graph, sorted global idx)."""
        nodes = np.unique(np.asarray(nodes, dtype=np.int64))
        local = np.full(self.n, -1, dtype=np.int64)
        local[nodes] = np.arange(len(nodes))
        starts, ends = self.indptr[nodes], self.indptr[nodes + 1]
        lengths = ends - starts
        if lengths.sum() == 0:
            empty = np.zeros(0, dtype=np.int64)
            return SparseGraph.from_edges(len(nodes), empty, empty, empty, empty), nodes
        edge_ids = np.concatenate([np.arange(a, b) for a, b in zip(starts, ends, strict=True)])
        pre_local = np.repeat(np.arange(len(nodes)), lengths)
        post_local = local[np.asarray(self.indices[edge_ids])]
        keep = post_local >= 0
        return (
            SparseGraph.from_edges(
                len(nodes),
                pre_local[keep],
                post_local[keep],
                np.asarray(self.syn_count[edge_ids])[keep],
                np.asarray(self.sign[edge_ids])[keep],
            ),
            nodes,
        )


@dataclass(frozen=True)
class CscIndex:
    indptr: np.ndarray
    edge_ids: np.ndarray
    pre: np.ndarray

    def in_edges(self, j: int) -> tuple[np.ndarray, np.ndarray]:
        s = slice(int(self.indptr[j]), int(self.indptr[j + 1]))
        return self.pre[s], self.edge_ids[s]


class GraphQueries:
    """Upstream/downstream/pathway queries over a :class:`SparseGraph`."""

    def __init__(self, graph: SparseGraph):
        self.g = graph
        self._csc: CscIndex | None = None

    @property
    def csc(self) -> CscIndex:
        if self._csc is None:
            self._csc = self.g.transpose_index()
        return self._csc

    def upstream(self, j: int, min_syn: int = 1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        pre, eids = self.csc.in_edges(j)
        cnt = np.asarray(self.g.syn_count[eids])
        sgn = np.asarray(self.g.sign[eids])
        keep = cnt >= min_syn
        return pre[keep], cnt[keep], sgn[keep]

    def downstream(self, i: int, min_syn: int = 1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self.g.downstream(i, min_syn)

    def neighborhood(
        self,
        seeds: np.ndarray,
        depth: int,
        direction: str = "downstream",
        min_syn: int = 5,
        max_nodes: int = 5000,
    ) -> dict[int, int]:
        """Breadth-first k-hop expansion. Returns {idx: hop distance}; stops at ``max_nodes``."""
        if direction not in ("downstream", "upstream", "both"):
            raise ValueError("direction must be downstream, upstream or both")
        dist = {int(s): 0 for s in np.atleast_1d(seeds)}
        frontier = deque(dist.keys())
        while frontier:
            node = frontier.popleft()
            d = dist[node]
            if d >= depth:
                continue
            nbrs: list[np.ndarray] = []
            if direction in ("downstream", "both"):
                nbrs.append(self.downstream(node, min_syn)[0])
            if direction in ("upstream", "both"):
                nbrs.append(self.upstream(node, min_syn)[0])
            for nb in np.concatenate(nbrs) if nbrs else []:
                nb = int(nb)
                if nb not in dist:
                    if len(dist) >= max_nodes:
                        return dist
                    dist[nb] = d + 1
                    frontier.append(nb)
        return dist

    def shortest_path(
        self, sources: np.ndarray, targets: np.ndarray, min_syn: int = 5, max_depth: int = 6
    ) -> list[int] | None:
        """Shortest directed path (in hops) from any source to any target, or None."""
        targets_set = {int(t) for t in np.atleast_1d(targets)}
        parent: dict[int, int] = {}
        frontier = deque()
        for s in np.atleast_1d(sources):
            parent[int(s)] = -1
            frontier.append((int(s), 0))
        while frontier:
            node, d = frontier.popleft()
            if node in targets_set:
                path = [node]
                while parent[path[-1]] != -1:
                    path.append(parent[path[-1]])
                return path[::-1]
            if d >= max_depth:
                continue
            for nb in self.downstream(node, min_syn)[0]:
                nb = int(nb)
                if nb not in parent:
                    parent[nb] = node
                    frontier.append((nb, d + 1))
        return None
