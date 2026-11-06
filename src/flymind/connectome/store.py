"""On-disk canonical dataset storage and loading.

Layout of ``data/processed/<dataset_id>/``::

    manifest.json            provenance (see manifest.py)
    neurons.parquet          NEURON_SCHEMA
    connections.parquet      CONNECTION_SCHEMA (source resolution; optional)
    edges.parquet            EDGE_SCHEMA (aggregated, sorted)
    csr_*.npy                SparseGraph arrays (memory-mappable)
    validation_report.json   output of validate.validate_dataset
"""

from __future__ import annotations

import functools
import threading
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from flymind.common.paths import processed_dir, safe_join, validate_identifier
from flymind.connectome.graph import GraphQueries, SparseGraph
from flymind.connectome.manifest import DatasetManifest
from flymind.connectome.schema import EDGE_SCHEMA, NEURON_SCHEMA


class DatasetNotFoundError(FileNotFoundError):
    pass


def dataset_dir(dataset_id: str, root: Path | None = None) -> Path:
    validate_identifier(dataset_id, "dataset id")
    return safe_join(root or processed_dir(), dataset_id)


def list_datasets(root: Path | None = None) -> list[DatasetManifest]:
    base = root or processed_dir()
    if not base.exists():
        return []
    manifests = []
    for child in sorted(base.iterdir()):
        mf = child / "manifest.json"
        if mf.is_file():
            try:
                manifests.append(DatasetManifest.read(mf))
            except ValueError:
                continue
    return manifests


def write_dataset(
    out_dir: Path,
    neurons: pd.DataFrame,
    edges: pd.DataFrame,
    manifest: DatasetManifest,
    connections: pa.Table | pd.DataFrame | None = None,
) -> None:
    """Persist canonical tables. ``neurons`` must already carry ``idx`` sorted by root_id."""
    out_dir.mkdir(parents=True, exist_ok=True)
    neurons = neurons.reindex(columns=[f.name for f in NEURON_SCHEMA])
    for f in NEURON_SCHEMA:
        col = neurons[f.name]
        if pa.types.is_string(f.type):
            neurons[f.name] = col.astype("object").where(col.notna(), None)
        elif pa.types.is_floating(f.type):
            neurons[f.name] = pd.to_numeric(col, errors="coerce").astype("float32")
    pq.write_table(
        pa.Table.from_pandas(neurons, schema=NEURON_SCHEMA, preserve_index=False),
        out_dir / "neurons.parquet",
        compression="zstd",
    )
    edges = edges.sort_values(["pre_idx", "post_idx"], kind="stable")
    pq.write_table(
        pa.Table.from_pandas(
            edges[[f.name for f in EDGE_SCHEMA]], schema=EDGE_SCHEMA, preserve_index=False
        ),
        out_dir / "edges.parquet",
        compression="zstd",
    )
    if connections is not None:
        table = (
            connections
            if isinstance(connections, pa.Table)
            else pa.Table.from_pandas(connections, preserve_index=False)
        )
        pq.write_table(table, out_dir / "connections.parquet", compression="zstd")
    graph = SparseGraph.from_edges(
        len(neurons),
        edges["pre_idx"].to_numpy(),
        edges["post_idx"].to_numpy(),
        edges["syn_count"].to_numpy(),
        edges["sign"].to_numpy(),
    )
    graph.save(out_dir)
    manifest.write(out_dir / "manifest.json")


class ConnectomeStore:
    """Read-only access to one processed dataset. Thread-safe lazy loading."""

    def __init__(self, directory: Path):
        if not (directory / "manifest.json").is_file():
            raise DatasetNotFoundError(f"no processed dataset at {directory}")
        self.directory = directory
        self.manifest = DatasetManifest.read(directory / "manifest.json")
        self._lock = threading.Lock()
        self._neurons: pd.DataFrame | None = None
        self._graph: SparseGraph | None = None
        self._queries: GraphQueries | None = None
        self._root_sorted: np.ndarray | None = None

    @classmethod
    def open(cls, dataset_id: str, root: Path | None = None) -> ConnectomeStore:
        return cls(dataset_dir(dataset_id, root))

    @property
    def dataset_id(self) -> str:
        return self.manifest.dataset_id

    # --------------------------------------------------------------- tables
    @property
    def neurons(self) -> pd.DataFrame:
        with self._lock:
            if self._neurons is None:
                df = pq.read_table(self.directory / "neurons.parquet").to_pandas()
                if not (df["idx"].to_numpy() == np.arange(len(df))).all():
                    raise ValueError("neurons.parquet idx column is not dense and ordered")
                self._neurons = df
                self._root_sorted = df["root_id"].to_numpy(dtype=np.int64)
            return self._neurons

    @property
    def graph(self) -> SparseGraph:
        with self._lock:
            if self._graph is None:
                self._graph = SparseGraph.load(self.directory, mmap=True)
            return self._graph

    @property
    def queries(self) -> GraphQueries:
        if self._queries is None:
            self._queries = GraphQueries(self.graph)
        return self._queries

    @property
    def n_neurons(self) -> int:
        return self.manifest.n_neurons

    def has_connections_table(self) -> bool:
        return (self.directory / "connections.parquet").is_file()

    # ------------------------------------------------------------- id mapping
    def root_to_idx(self, root_ids: np.ndarray | list[int], strict: bool = True) -> np.ndarray:
        """Map int64 root IDs to dense idx. Unknown IDs raise (strict) or map to -1."""
        _ = self.neurons
        assert self._root_sorted is not None
        ids = np.asarray(root_ids, dtype=np.int64)
        pos = np.searchsorted(self._root_sorted, ids)
        pos_clip = np.minimum(pos, len(self._root_sorted) - 1)
        found = self._root_sorted[pos_clip] == ids
        if strict and not found.all():
            missing = ids[~found][:5].tolist()
            raise KeyError(f"unknown root id(s) in {self.dataset_id}: {missing}")
        return np.where(found, pos_clip, -1).astype(np.int64)

    def idx_to_root(self, idx: np.ndarray | list[int]) -> np.ndarray:
        return self.neurons["root_id"].to_numpy(dtype=np.int64)[np.asarray(idx, dtype=np.int64)]

    # ------------------------------------------------------------------ duckdb
    @functools.cached_property
    def _duck(self) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect(database=":memory:")
        for name in ("neurons", "edges", "connections"):
            path = self.directory / f"{name}.parquet"
            if path.is_file():
                con.execute(
                    f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path.as_posix()}')"
                )
        return con

    def sql(self, query: str, params: list | None = None) -> pd.DataFrame:
        """Run a read-only analytical query (internal use; never exposed to API input)."""
        with self._lock:
            cur = self._duck.cursor()
        return cur.execute(query, params or []).fetchdf()

    def neuropil_summary(self) -> pd.DataFrame:
        if self.has_connections_table():
            return self.sql(
                "SELECT neuropil, SUM(syn_count)::BIGINT AS synapses, COUNT(*) AS connections "
                "FROM connections WHERE neuropil IS NOT NULL GROUP BY neuropil "
                "ORDER BY synapses DESC"
            )
        return self.sql(
            "SELECT primary_neuropil AS neuropil, COUNT(*) AS neurons FROM neurons "
            "WHERE primary_neuropil IS NOT NULL GROUP BY 1 ORDER BY neurons DESC"
        )


_STORE_CACHE: dict[tuple[str, str], ConnectomeStore] = {}
_STORE_LOCK = threading.Lock()


def get_store(dataset_id: str, root: Path | None = None) -> ConnectomeStore:
    """Process-wide cached store (datasets are immutable once imported)."""
    directory = dataset_dir(dataset_id, root)
    key = (dataset_id, str(directory))
    with _STORE_LOCK:
        store = _STORE_CACHE.get(key)
        if store is None:
            store = ConnectomeStore(directory)
            _STORE_CACHE[key] = store
        return store


def clear_store_cache() -> None:
    with _STORE_LOCK:
        _STORE_CACHE.clear()
