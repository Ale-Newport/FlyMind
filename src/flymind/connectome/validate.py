"""Dataset integrity validation and import reports."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pyarrow.parquet as pq

from flymind.common.provenance import utc_now
from flymind.connectome.graph import SparseGraph
from flymind.connectome.manifest import DatasetManifest

Status = Literal["pass", "warn", "fail", "skip"]

# Published reference statistics for dataset-specific checks.
EXPECTED_STATS: dict[str, dict[str, int]] = {
    # FlyWire FAFB v783 public release: 139,255 proofread neurons (Dorkenwald et al. 2024).
    "flywire_fafb_783": {"n_neurons": 139_255},
}


@dataclass
class Check:
    name: str
    status: Status
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class ValidationReport:
    dataset_id: str
    created_at: str
    checks: list[Check]
    statistics: dict[str, object]

    @property
    def status(self) -> Literal["passed", "passed_with_warnings", "failed"]:
        if any(c.status == "fail" for c in self.checks):
            return "failed"
        if any(c.status == "warn" for c in self.checks):
            return "passed_with_warnings"
        return "passed"

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "created_at": self.created_at,
            "status": self.status,
            "statistics": self.statistics,
            "checks": [asdict(c) for c in self.checks],
        }

    def to_markdown(self) -> str:
        icon = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}
        lines = [
            f"# Validation report: `{self.dataset_id}`",
            "",
            f"- Generated: {self.created_at}",
            f"- Overall status: **{self.status}**",
            "",
            "## Statistics",
            "",
            "| Statistic | Value |",
            "|---|---|",
        ]
        lines += [f"| {k} | {v} |" for k, v in self.statistics.items()]
        lines += ["", "## Checks", "", "| Status | Check | Result |", "|---|---|---|"]
        lines += [f"| {icon[c.status]} | {c.name} | {c.message} |" for c in self.checks]
        return "\n".join(lines) + "\n"

    def write(self, directory: Path) -> None:
        (directory / "validation_report.json").write_text(
            json.dumps(self.to_dict(), indent=2, default=_jsonable) + "\n"
        )
        (directory / "validation_report.md").write_text(self.to_markdown())


def _jsonable(obj: object) -> object:
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


def float_corruption_suspected(ids: np.ndarray) -> bool:
    """Detect int64 IDs that were round-tripped through float64.

    float64 has a 53-bit mantissa, so integers above 2**53 that passed through a
    float lose their low bits and become multiples of a power of two (>= 2 for
    values > 2**53, >= 64 for ~7e17 FlyWire IDs). Genuine IDs are multiples of 64
    only ~1/64 of the time.
    """
    big = ids[np.abs(ids) > 2**53]
    if len(big) < 50:
        return False
    frac = float(np.mean(big % 64 == 0))
    return frac > 0.5


def validate_dataset(directory: Path) -> ValidationReport:
    manifest = DatasetManifest.read(directory / "manifest.json")
    checks: list[Check] = []
    neurons = pq.read_table(directory / "neurons.parquet").to_pandas()
    graph = SparseGraph.load(directory, mmap=False)
    n = len(neurons)

    # --- identifiers --------------------------------------------------------
    rid = neurons["root_id"]
    checks.append(
        Check(
            "root_id dtype is int64",
            "pass" if str(rid.dtype) == "int64" else "fail",
            f"dtype={rid.dtype}",
        )
    )
    n_dup = int(rid.duplicated().sum())
    checks.append(
        Check(
            "unique neuron identifiers",
            "pass" if n_dup == 0 else "fail",
            f"{n_dup} duplicated root_id values",
            {"duplicates": int(n_dup)},
        )
    )
    checks.append(
        Check(
            "no missing identifiers",
            "pass" if not rid.isna().any() else "fail",
            f"{int(rid.isna().sum())} null root_id values",
        )
    )
    corrupted = float_corruption_suspected(rid.to_numpy(dtype=np.int64))
    checks.append(
        Check(
            "no float64 identifier corruption",
            "fail" if corrupted else "pass",
            "IDs look like float-rounded integers"
            if corrupted
            else "low-bit distribution consistent with exact int64 IDs",
        )
    )
    idx_ok = (neurons["idx"].to_numpy() == np.arange(n)).all()
    sorted_ok = bool((np.diff(rid.to_numpy(dtype=np.int64)) > 0).all()) if n > 1 else True
    checks.append(
        Check(
            "dense idx sorted by root_id",
            "pass" if idx_ok and sorted_ok else "fail",
            "idx == 0..N-1 and root_id strictly increasing"
            if idx_ok and sorted_ok
            else "idx/root_id ordering broken",
        )
    )

    # --- edges --------------------------------------------------------------
    ok_shape = graph.n == n and len(graph.indptr) == n + 1
    checks.append(
        Check(
            "CSR matches neuron table",
            "pass" if ok_shape else "fail",
            f"graph.n={graph.n}, neurons={n}",
        )
    )
    in_range = graph.n_edges == 0 or (graph.indices.min() >= 0 and graph.indices.max() < n)
    checks.append(
        Check(
            "edge endpoints valid",
            "pass" if in_range else "fail",
            "all postsynaptic indices within [0, N)" if in_range else "out-of-range indices",
        )
    )
    pre = graph.pre_indices()
    key = pre.astype(np.int64) * n + graph.indices.astype(np.int64)
    n_dup_edges = int(len(key) - len(np.unique(key)))
    checks.append(
        Check(
            "no duplicated aggregated edges",
            "pass" if n_dup_edges == 0 else "fail",
            f"{n_dup_edges} duplicate (pre, post) pairs",
        )
    )
    nonpos = int((graph.syn_count <= 0).sum())
    checks.append(
        Check(
            "positive synapse counts",
            "pass" if nonpos == 0 else "fail",
            f"{nonpos} edges with syn_count <= 0",
        )
    )
    bad_sign = int((~np.isin(graph.sign, (-1, 1))).sum())
    checks.append(
        Check(
            "edge signs in {-1, +1}",
            "pass" if bad_sign == 0 else "fail",
            f"{bad_sign} edges with invalid sign",
        )
    )
    n_self = int((pre == graph.indices).sum())
    checks.append(
        Check(
            "self-connections reported",
            "pass",
            f"{n_self} autaptic edges kept as reconstructed (not removed)",
            {"autapses": n_self},
        )
    )
    sign_consistent = True
    if graph.n_edges:
        # A neuron's sign is defined by its (predicted) transmitter: all its out-edges agree.
        first = np.asarray(graph.sign)[graph.indptr[:-1][np.diff(graph.indptr) > 0]]
        per_edge_first = np.repeat(first, np.diff(graph.indptr)[np.diff(graph.indptr) > 0])
        sign_consistent = bool((per_edge_first == graph.sign).all())
    checks.append(
        Check(
            "presynaptic sign consistency (Dale's principle assumption)",
            "pass" if sign_consistent else "warn",
            "every neuron's outgoing edges share one sign"
            if sign_consistent
            else "some neurons have mixed-sign outputs (per-connection NT predictions)",
        )
    )

    # --- source-resolution table consistency --------------------------------
    conn_path = directory / "connections.parquet"
    if conn_path.is_file():
        conn = pq.read_table(conn_path, columns=["pre_root_id", "post_root_id", "syn_count"])
        conn_syn = int(np.asarray(conn["syn_count"], dtype=np.int64).sum())
        checks.append(
            Check(
                "aggregated synapse total matches source rows",
                "pass" if conn_syn == graph.n_synapses else "fail",
                f"source={conn_syn}, aggregated={graph.n_synapses}",
            )
        )
        ids = np.unique(
            np.concatenate(
                [
                    np.asarray(conn["pre_root_id"], dtype=np.int64),
                    np.asarray(conn["post_root_id"], dtype=np.int64),
                ]
            )
        )
        missing = int((~np.isin(ids, rid.to_numpy(dtype=np.int64))).sum())
        checks.append(
            Check(
                "connection endpoints exist in neuron table",
                "pass" if missing == 0 else "fail",
                f"{missing} connection root_ids absent from neuron table",
            )
        )
    else:
        checks.append(
            Check(
                "aggregated synapse total matches source rows",
                "skip",
                "no source-resolution connections table stored",
            )
        )

    # --- coordinates ----------------------------------------------------------
    pos = neurons[["pos_x", "pos_y", "pos_z"]].to_numpy(dtype=np.float64)
    has_pos = ~np.isnan(pos).any(axis=1)
    finite = np.isfinite(pos[has_pos]).all()
    checks.append(
        Check(
            "anatomical coordinates finite",
            "pass" if finite else "fail",
            f"{int(has_pos.sum())}/{n} neurons have a position",
            {"with_position": int(has_pos.sum())},
        )
    )
    if has_pos.any():
        lo, hi = pos[has_pos].min(axis=0), pos[has_pos].max(axis=0)
        plausible = bool((hi - lo).max() < 5e6) or manifest.synthetic
        checks.append(
            Check(
                "coordinate extent plausible (< 5 mm)",
                "pass" if plausible else "warn",
                f"extent nm = {np.round(hi - lo).tolist()}",
            )
        )

    # --- dataset-specific expectations --------------------------------------
    expected = EXPECTED_STATS.get(manifest.dataset_id)
    if expected:
        for key_name, value in expected.items():
            actual = {"n_neurons": n}.get(key_name)
            checks.append(
                Check(
                    f"expected {key_name} for {manifest.dataset_id}",
                    "pass" if actual == value else "warn",
                    f"expected {value}, found {actual}",
                )
            )
    if manifest.synthetic:
        checks.append(
            Check(
                "synthetic dataset flagged",
                "pass",
                "dataset is SYNTHETIC; it does not represent any real specimen",
            )
        )

    stats = {
        "neurons": n,
        "aggregated_edges": graph.n_edges,
        "synapses": graph.n_synapses,
        "inhibitory_edge_fraction": round(float(np.mean(graph.sign < 0)), 4)
        if graph.n_edges
        else 0,
        "mean_out_degree": round(graph.n_edges / max(n, 1), 2),
        "max_out_degree": int(np.diff(graph.indptr).max()) if n else 0,
        "neurons_without_edges": int(
            ((np.diff(graph.indptr) == 0) & (np.bincount(graph.indices, minlength=n) == 0)).sum()
        ),
    }
    if "super_class" in neurons:
        stats["super_classes"] = int(neurons["super_class"].nunique())
    if "cell_type" in neurons:
        stats["cell_types"] = int(neurons["cell_type"].nunique())
    return ValidationReport(manifest.dataset_id, utc_now(), checks, stats)


def validate_and_record(directory: Path) -> ValidationReport:
    report = validate_dataset(directory)
    report.write(directory)
    manifest = DatasetManifest.read(directory / "manifest.json")
    manifest.validation_status = report.status
    manifest.write(directory / "manifest.json")
    return report
