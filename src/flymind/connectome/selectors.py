"""Neuron selection by identifier, annotation, region, transmitter or connectivity.

Selections are stored in experiment specs as :class:`NeuronSelector` (root IDs and
annotation filters, never dense indices), so a spec stays valid and reproducible
for a given dataset version.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field, field_validator

from flymind.common.paths import repo_root
from flymind.connectome.store import ConnectomeStore

GROUPS_DIR = repo_root() / "data" / "manifests" / "groups"


class ConnectivityCriterion(BaseModel):
    direction: str = Field("downstream", pattern="^(downstream|upstream)$")
    of: NeuronSelector
    min_syn: int = Field(5, ge=1)


class NeuronSelector(BaseModel):
    """All given filters are combined with AND; ``root_ids`` and ``group`` add explicitly."""

    root_ids: list[int] = []
    group: str | None = Field(None, description="named group from the dataset's group file")
    cell_types: list[str] = []
    cell_type_regex: str | None = None
    hemibrain_types: list[str] = []
    super_class: list[str] = []
    cell_class: list[str] = []
    side: list[str] = []
    nt_type: list[str] = []
    neuropils: list[str] = []
    connected: ConnectivityCriterion | None = None
    limit: int | None = Field(None, ge=1, le=200_000)

    @field_validator("cell_type_regex")
    @classmethod
    def _regex_ok(cls, v: str | None) -> str | None:
        if v is not None:
            if len(v) > 200:
                raise ValueError("regex too long")
            re.compile(v)
        return v

    def is_empty(self) -> bool:
        return not (
            self.root_ids
            or self.group
            or self.cell_types
            or self.cell_type_regex
            or self.hemibrain_types
            or self.super_class
            or self.cell_class
            or self.side
            or self.nt_type
            or self.neuropils
            or self.connected
        )


ConnectivityCriterion.model_rebuild()


def load_groups(dataset_id: str) -> dict[str, dict]:
    """Curated groups (``<id>.json``, committed) merged with user groups (``<id>.user.json``)."""
    groups: dict[str, dict] = {}
    for suffix in (".json", ".user.json"):
        path = GROUPS_DIR / f"{dataset_id}{suffix}"
        if path.is_file():
            groups.update(json.loads(path.read_text())["groups"])
    return groups


def resolve(store: ConnectomeStore, sel: NeuronSelector) -> np.ndarray:
    """Return sorted dataset idx matching ``sel``."""
    nb = store.neurons
    n = len(nb)
    explicit = np.zeros(0, dtype=np.int64)
    if sel.root_ids:
        explicit = store.root_to_idx(sel.root_ids, strict=True)
    if sel.group:
        groups = load_groups(store.dataset_id)
        if sel.group not in groups:
            raise KeyError(f"unknown group {sel.group!r} for {store.dataset_id}")
        g = groups[sel.group]
        if g.get("root_ids"):
            explicit = np.concatenate([explicit, store.root_to_idx(g["root_ids"], strict=False)])
            explicit = explicit[explicit >= 0]
        if g.get("selector"):
            explicit = np.concatenate([explicit, resolve(store, NeuronSelector(**g["selector"]))])
    has_filters = any(
        [
            sel.cell_types,
            sel.cell_type_regex,
            sel.hemibrain_types,
            sel.super_class,
            sel.cell_class,
            sel.side,
            sel.nt_type,
            sel.neuropils,
            sel.connected,
        ]
    )
    if has_filters:
        mask = np.ones(n, dtype=bool)

        def isin(col: str, values: list[str]) -> np.ndarray:
            if col not in nb:
                return np.zeros(n, dtype=bool)
            return nb[col].isin(values).to_numpy()

        if sel.cell_types:
            mask &= isin("cell_type", sel.cell_types)
        if sel.cell_type_regex:
            mask &= (
                nb["cell_type"].fillna("").str.contains(sel.cell_type_regex, regex=True).to_numpy()
            )
        if sel.hemibrain_types:
            mask &= isin("hemibrain_type", sel.hemibrain_types)
        if sel.super_class:
            mask &= isin("super_class", sel.super_class)
        if sel.cell_class:
            mask &= isin("cell_class", sel.cell_class)
        if sel.side:
            mask &= isin("side", sel.side)
        if sel.nt_type:
            mask &= isin("nt_type", [s.upper() for s in sel.nt_type])
        if sel.neuropils:
            mask &= isin("primary_neuropil", sel.neuropils)
        if sel.connected is not None:
            src = resolve(store, sel.connected.of)
            hit = np.zeros(n, dtype=bool)
            q = store.queries
            for i in src:
                nbrs = (
                    q.downstream(int(i), sel.connected.min_syn)[0]
                    if sel.connected.direction == "downstream"
                    else q.upstream(int(i), sel.connected.min_syn)[0]
                )
                hit[nbrs] = True
            mask &= hit
        filtered = np.nonzero(mask)[0]
    else:
        filtered = np.zeros(0, dtype=np.int64)
    out = np.unique(np.concatenate([explicit, filtered]).astype(np.int64))
    if sel.limit is not None:
        out = out[: sel.limit]
    return out


def save_group(
    dataset_id: str,
    name: str,
    root_ids: list[int],
    description: str,
    source: str,
    groups_dir: Path | None = None,
) -> None:
    """Persist a user-defined group (root IDs) next to the curated groups."""
    from flymind.common.paths import validate_identifier

    validate_identifier(name, "group name")
    directory = groups_dir or GROUPS_DIR
    path = directory / f"{dataset_id}.user.json"
    data = json.loads(path.read_text()) if path.is_file() else {"groups": {}}
    data["groups"][name] = {
        "root_ids": [int(r) for r in root_ids],
        "description": description,
        "source": source,
        "user_defined": True,
    }
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
