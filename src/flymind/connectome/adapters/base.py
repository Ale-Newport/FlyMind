"""Dataset adapter interface.

An adapter turns a set of recognised source files (see ``detect.py``) for ONE
specimen and ONE release into the canonical tables of ``schema.py``. Adapters must
never mix identifiers from different specimens or releases; they verify that every
identifier referenced by any input file belongs to the dataset's neuron set.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from flymind.connectome.detect import DetectedFile

SupportStatus = Literal["supported", "planned"]


@dataclass(frozen=True)
class AdapterInfo:
    name: str
    dataset_id: str
    title: str
    specimen: str
    status: SupportStatus
    description: str
    required_roles: tuple[str, ...]
    optional_roles: tuple[str, ...] = ()


class DatasetAdapter(ABC):
    info: AdapterInfo

    def accepts(self, files: list[DetectedFile]) -> bool:
        roles = {f.role for f in files}
        return any(r in roles for r in self.info.required_roles)

    @abstractmethod
    def build(self, files: list[DetectedFile], out_root: Path, **options) -> Path:
        """Import ``files`` and write ``out_root/<dataset_id>``; returns that directory."""


class PlannedAdapter(DatasetAdapter):
    """Declared but not implemented: refuses to import rather than guessing."""

    def accepts(self, files: list[DetectedFile]) -> bool:
        return False

    def build(self, files: list[DetectedFile], out_root: Path, **options) -> Path:
        raise NotImplementedError(
            f"{self.info.title} is planned but not yet supported: an adapter is only "
            "enabled after dataset-specific validation (see docs/scientific/connectome-sources.md)."
        )
