"""Recognise connectome source files from their contents (headers / schemas), not names."""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path

import pyarrow.feather as pf
import pyarrow.parquet as pq


@dataclass(frozen=True)
class DetectedFile:
    path: Path
    role: str
    format: str
    columns: tuple[str, ...]
    description: str


# role -> (required columns, description). Order matters: first match wins.
_CSV_ROLES: list[tuple[str, frozenset[str], str]] = [
    (
        "codex_connections",
        frozenset({"pre_root_id", "post_root_id", "neuropil", "syn_count", "nt_type"}),
        "Codex connections (per neuropil)",
    ),
    (
        "codex_neurons",
        frozenset({"root_id", "group", "nt_type", "nt_type_score"}),
        "Codex neurons (transmitter predictions)",
    ),
    (
        "codex_classification_types",
        frozenset(
            {"root_id", "flow", "super_class", "class", "sub_class", "cell_type", "hemibrain_type"}
        ),
        "Codex classification with cell types",
    ),
    (
        "codex_classification",
        frozenset({"root_id", "flow", "super_class", "class", "sub_class", "side"}),
        "Codex classification",
    ),
    ("codex_cell_types", frozenset({"root_id", "primary_type"}), "Codex consolidated cell types"),
    (
        "codex_coordinates",
        frozenset({"root_id", "position", "supervoxel_id"}),
        "Codex representative coordinates (nm)",
    ),
    ("codex_names", frozenset({"root_id", "name", "group"}), "Codex neuron names"),
    (
        "codex_cell_stats",
        frozenset({"root_id", "length_nm", "area_nm", "size_nm"}),
        "Codex morphology statistics",
    ),
    (
        "annotations_tsv",
        frozenset({"root_id", "supervoxel_id", "pos_x", "super_class", "cell_type", "top_nt"}),
        "FlyWire community annotations (Schlegel et al. 2024)",
    ),
    ("shiu_completeness", frozenset({"", "Completed"}), "Shiu et al. 2024 neuron list"),
    (
        "codex_labels",
        frozenset({"root_id", "label", "user_id", "user_name"}),
        "Codex community labels (contains personal data; not imported)",
    ),
]

_TABLE_ROLES: list[tuple[str, frozenset[str], str]] = [
    (
        "shiu_connectivity",
        frozenset(
            {
                "Presynaptic_ID",
                "Postsynaptic_ID",
                "Presynaptic_Index",
                "Postsynaptic_Index",
                "Connectivity",
                "Excitatory",
            }
        ),
        "Shiu et al. 2024 signed connectivity",
    ),
    (
        "zenodo_connections",
        frozenset({"pre_pt_root_id", "post_pt_root_id", "neuropil", "syn_count"}),
        "Zenodo proofread connections",
    ),
    (
        "zenodo_neuropil_pre",
        frozenset({"pre_pt_root_id", "neuropil", "count"}),
        "Zenodo per-neuron presynapse counts by neuropil",
    ),
    (
        "zenodo_neuropil_post",
        frozenset({"post_pt_root_id", "neuropil", "count"}),
        "Zenodo per-neuron postsynapse counts by neuropil",
    ),
]


def _first_line(path: Path) -> str:
    with path.open("rb") as raw:
        magic = raw.read(2)
    opener = gzip.open if magic == b"\x1f\x8b" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as fh:
        return fh.readline().rstrip("\r\n")


def detect_file(path: Path) -> DetectedFile | None:
    path = Path(path)
    if not path.is_file():
        return None
    with path.open("rb") as fh:
        head = fh.read(8)
    try:
        if head[:4] == b"PAR1":
            cols = tuple(pq.read_schema(path).names)
            fmt = "parquet"
        elif head[:6] == b"ARROW1":
            cols = tuple(pf.read_table(path, memory_map=True).schema.names)
            fmt = "feather"
        elif head[:6] == b"\x93NUMPY":
            return DetectedFile(path, "zenodo_root_ids", "npy", (), "NumPy root-id array")
        else:
            line = _first_line(path)
            sep = "\t" if line.count("\t") > line.count(",") else ","
            cols = tuple(c.strip().strip('"') for c in line.split(sep))
            fmt = "tsv" if sep == "\t" else "csv"
            for role, required, desc in _CSV_ROLES:
                if required <= set(cols):
                    return DetectedFile(path, role, fmt, cols, desc)
            return None
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    for role, required, desc in _TABLE_ROLES:
        if required <= set(cols):
            return DetectedFile(path, role, fmt, cols, desc)
    return None


def scan_directory(directory: Path) -> list[DetectedFile]:
    found = []
    for path in sorted(Path(directory).rglob("*")):
        if path.is_file() and not path.name.startswith(".") and not path.name.endswith(".part"):
            det = detect_file(path)
            if det is not None:
                found.append(det)
    return found
