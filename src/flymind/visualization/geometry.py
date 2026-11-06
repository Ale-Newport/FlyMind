"""Anatomy geometry for the 3D explorer.

Raw vs visualisation representations are kept separate:

* raw: the source skeleton parquet (nm, float32, one row per node), untouched;
* indexed: the same rows re-chunked into small row groups + a neuron index
  (``skeleton_index.npz``), lossless;
* visualisation: per request, a level-of-detail simplification (topology-preserving
  decimation of unbranched runs) converted to micrometres as float32 line segments.

Precision: nm -> um float32 conversion keeps ~1e-7 relative precision (sub-nm at
brain scale); decimation removes intermediate nodes only, keeping every root,
branch point and leaf, so path topology is preserved but curvature between kept
nodes is linearised. Both are reported in each response.
"""

from __future__ import annotations

import base64
import threading
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from flymind.common.logging import get_logger
from flymind.common.paths import cache_dir, raw_dir
from flymind.connectome.store import ConnectomeStore

log = get_logger("visualization.geometry")

SKELETON_RAW = "flywire-783-skeletons/sk_lod1_783_healed_ds2.parquet"
SKELETON_DATASET = "flywire_fafb_783"
INDEX_ROW_GROUP = 131_072


def skeleton_store_dir() -> Path:
    return cache_dir() / "skeletons" / SKELETON_DATASET


class SkeletonUnavailableError(FileNotFoundError):
    pass


def build_skeleton_index(
    raw_path: Path | None = None, out_dir: Path | None = None, progress=None
) -> Path:
    """Re-chunk the (neuron-sorted) source parquet and index rows by neuron."""
    raw_path = raw_path or raw_dir() / SKELETON_RAW
    out_dir = out_dir or skeleton_store_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    src = pq.ParquetFile(raw_path)
    cols = ["neuron", "node_id", "parent_id", "x", "y", "z", "radius"]
    tmp = out_dir / "skeletons.parquet.part"
    writer = None
    neurons: list[np.ndarray] = []
    n_rows = 0
    try:
        for k, batch in enumerate(src.iter_batches(batch_size=INDEX_ROW_GROUP, columns=cols)):
            table = pa.Table.from_batches([batch])
            if writer is None:
                writer = pq.ParquetWriter(tmp, table.schema, compression="zstd")
            writer.write_table(table, row_group_size=INDEX_ROW_GROUP)
            neurons.append(batch.column("neuron").to_numpy())
            n_rows += batch.num_rows
            if progress and k % 100 == 0:
                progress(f"indexed {n_rows:,} / {src.metadata.num_rows:,} nodes")
    finally:
        if writer is not None:
            writer.close()
    neuron = np.concatenate(neurons).astype(np.int64)
    change = np.nonzero(np.diff(neuron))[0] + 1
    starts = np.concatenate([[0], change])
    ids = neuron[starts]
    counts = np.diff(np.concatenate([starts, [len(neuron)]]))
    if len(np.unique(ids)) != len(ids):
        raise ValueError("source skeleton file is not grouped by neuron")
    order = np.argsort(ids)
    soma = {}
    md = src.metadata.metadata or {}
    for key, val in md.items():
        if key.endswith(b":soma"):
            try:
                soma[int(key.split(b":")[0])] = int(val)
            except ValueError:
                continue
    soma_ids = np.array(list(soma.keys()), dtype=np.int64)
    soma_nodes = np.array(list(soma.values()), dtype=np.int64)
    np.savez(
        out_dir / "skeleton_index.npz",
        root_id=ids[order],
        start=starts[order],
        count=counts[order],
        soma_root=soma_ids,
        soma_node=soma_nodes,
        row_group_size=np.int64(INDEX_ROW_GROUP),
    )
    tmp.replace(out_dir / "skeletons.parquet")
    return out_dir


class SkeletonStore:
    _instance: SkeletonStore | None = None
    _lock = threading.Lock()

    def __init__(self, directory: Path):
        idx = np.load(directory / "skeleton_index.npz")
        self.root_id = idx["root_id"]
        self.start = idx["start"]
        self.count = idx["count"]
        self.rg = int(idx["row_group_size"])
        self.soma = dict(zip(idx["soma_root"].tolist(), idx["soma_node"].tolist(), strict=True))
        self.file = pq.ParquetFile(directory / "skeletons.parquet")
        self._file_lock = threading.Lock()

    @classmethod
    def get(cls) -> SkeletonStore:
        with cls._lock:
            if cls._instance is None:
                d = skeleton_store_dir()
                if not (d / "skeleton_index.npz").is_file():
                    raise SkeletonUnavailableError(
                        "FlyWire skeletons are not installed. Run: uv run flymind data fetch "
                        "skeletons  (5.4 GB download from Zenodo "
                        "10.5281/zenodo.10877326, CC BY 4.0)"
                    )
                cls._instance = cls(d)
            return cls._instance

    def has(self, root_id: int) -> bool:
        i = np.searchsorted(self.root_id, root_id)
        return i < len(self.root_id) and self.root_id[i] == root_id

    def nodes(self, root_id: int) -> pd.DataFrame:
        i = np.searchsorted(self.root_id, root_id)
        if not (i < len(self.root_id) and self.root_id[i] == root_id):
            raise KeyError(f"no skeleton for {root_id}")
        a, n = int(self.start[i]), int(self.count[i])
        g0, g1 = a // self.rg, (a + n - 1) // self.rg
        with self._file_lock:
            t = self.file.read_row_groups(
                list(range(g0, g1 + 1)), columns=["node_id", "parent_id", "x", "y", "z", "radius"]
            )
        off = a - g0 * self.rg
        return t.slice(off, n).to_pandas()


def simplify(nodes: pd.DataFrame, keep_every: int) -> tuple[np.ndarray, np.ndarray, int]:
    """Decimate unbranched runs, keeping roots, branch points and leaves.

    Returns (kept node positions (k,3) nm, parent index into kept (-1 root), n kept).
    The parent of a kept node is its nearest kept ancestor. Handles files where a
    parent row appears after its child.
    """
    node_id = nodes["node_id"].to_numpy(np.int64)
    parent = nodes["parent_id"].to_numpy(np.int64)
    pos = nodes[["x", "y", "z"]].to_numpy(np.float64)
    order = np.argsort(node_id)
    sorted_ids = node_id[order]
    pi = np.searchsorted(sorted_ids, parent)
    pi = np.clip(pi, 0, len(sorted_ids) - 1)
    has_parent = (parent >= 0) & (sorted_ids[pi] == parent)
    parent_row = np.where(has_parent, order[pi], -1)
    n = len(node_id)
    n_children = np.bincount(parent_row[parent_row >= 0], minlength=n)
    keep = (parent_row < 0) | (n_children != 1)
    if keep_every > 1:
        # depth along chains: keep every k-th node by a cheap hash of row order
        keep |= (np.arange(n) % keep_every) == 0
    else:
        keep[:] = True
    # nearest kept ancestor (iterative pointer jumping)
    anc = np.where(parent_row >= 0, parent_row, -1)
    target = anc.copy()
    for _ in range(64):
        need = (target >= 0) & ~keep[np.maximum(target, 0)]
        if not need.any():
            break
        target[need] = anc[target[need]]
    kept_rows = np.nonzero(keep)[0]
    new_index = np.full(n, -1, dtype=np.int64)
    new_index[kept_rows] = np.arange(len(kept_rows))
    kp = target[kept_rows]
    kp = np.where(kp >= 0, new_index[np.maximum(kp, 0)], -1)
    return pos[kept_rows], kp, len(kept_rows)


LOD_KEEP = {0: 1, 1: 3, 2: 8}


def skeleton_payload(root_id: int, lod: int = 1) -> dict:
    store = SkeletonStore.get()
    nodes = store.nodes(root_id)
    keep_every = LOD_KEEP.get(lod, 3)
    pos, parent, k = simplify(nodes, keep_every)
    child = np.nonzero(parent >= 0)[0]
    seg = np.empty((len(child), 2, 3), dtype=np.float32)
    seg[:, 0] = pos[child] / 1000.0
    seg[:, 1] = pos[parent[child]] / 1000.0
    soma_xyz = None
    soma_node = store.soma.get(int(root_id))
    if soma_node is not None:
        hit = nodes.index[nodes["node_id"] == soma_node]
        if len(hit):
            soma_xyz = (nodes.loc[hit[0], ["x", "y", "z"]].to_numpy(float) / 1000.0).tolist()
    return {
        "root_id": str(root_id),
        "units": "um",
        "source": "FlyWire v783 skeletons (Schlegel et al. 2024; Zenodo 10.5281/zenodo.10877326, "
        "CC BY 4.0): healed, 2x downsampled L2 skeletons",
        "lod": lod,
        "simplification": {
            "original_nodes": len(nodes),
            "kept_nodes": int(k),
            "method": f"kept roots, branch points, leaves and every {keep_every}th node",
        },
        "precision": "float32 micrometres (source float32 nanometres)",
        "n_segments": len(child),
        "segments_b64": base64.b64encode(seg.tobytes()).decode(),
        "soma_um": soma_xyz,
    }


# ------------------------------------------------------------------ point cloud
CATEGORY_FIELDS = ("super_class", "primary_neuropil", "nt_type", "side", "cell_class", "flow")


def positions_um(store: ConnectomeStore) -> np.ndarray:
    nb = store.neurons
    return (nb[["pos_x", "pos_y", "pos_z"]].to_numpy(np.float64) / 1000.0).astype(np.float32)


def category_codes(store: ConnectomeStore, field: str, top: int = 254) -> dict:
    nb = store.neurons
    if field == "cell_type":
        col = nb["cell_type"].fillna("unannotated")
        common = col.value_counts().head(top).index
        col = col.where(col.isin(common), "other")
    elif field in CATEGORY_FIELDS:
        col = nb[field].fillna("unknown").astype(str)
    else:
        raise KeyError(field)
    cats = pd.Categorical(col)
    counts = pd.Series(cats.codes).value_counts().reindex(range(len(cats.categories)), fill_value=0)
    codes = cats.codes.astype(np.uint16)
    return {
        "field": field,
        "labels": [str(c) for c in cats.categories],
        "counts": counts.astype(int).tolist(),
        "codes_b64": base64.b64encode(codes.tobytes()).decode(),
    }


def neuropil_centroids(store: ConnectomeStore) -> list[dict]:
    nb = store.neurons
    if not nb["primary_neuropil"].notna().any():
        return []
    g = nb.dropna(subset=["primary_neuropil", "pos_x"]).groupby("primary_neuropil")
    agg = g[["pos_x", "pos_y", "pos_z"]].median() / 1000.0
    size = g.size()
    return [
        {"neuropil": k, "centroid_um": [float(v) for v in agg.loc[k]], "neurons": int(size[k])}
        for k in agg.index
    ]
