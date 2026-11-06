"""Machine-readable dataset provenance manifest (``manifest.json``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

MANIFEST_VERSION = 1


class SourceFile(BaseModel):
    name: str
    role: str
    sha256: str
    size_bytes: int
    detected_format: str
    url: str | None = None


class Citation(BaseModel):
    text: str
    doi: str | None = None


class DatasetManifest(BaseModel):
    manifest_version: int = MANIFEST_VERSION
    dataset_id: str
    dataset_name: str
    dataset_version: str
    specimen: str
    adapter: str
    synthetic: bool = False
    subset_of: str | None = Field(
        default=None,
        description="Set when this is a subset of a larger dataset (never full-brain).",
    )
    source: str
    source_urls: list[str] = []
    license: str
    citations: list[Citation] = []
    downloaded_at: str | None = None
    imported_at: str
    files: list[SourceFile] = []
    transformations: list[str] = []
    filters: dict[str, object] = {}
    sign_policy: dict[str, int] = {}
    sign_policy_source: str = ""
    n_neurons: int
    n_source_connections: int
    n_edges: int
    n_synapses: int
    position_units: str = "nm"
    processing: dict[str, object] = {}
    validation_status: Literal["passed", "passed_with_warnings", "failed", "not_run"] = "not_run"
    notes: list[str] = []

    def write(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2) + "\n")

    @classmethod
    def read(cls, path: Path) -> DatasetManifest:
        return cls.model_validate(json.loads(path.read_text()))
