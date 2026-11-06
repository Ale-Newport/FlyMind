"""Filesystem layout and safe path resolution.

All data paths are resolved relative to a single data root (``FLYMIND_DATA_DIR``,
default ``<repo>/data``). API endpoints only ever address files through dataset and
experiment identifiers, never through user-supplied paths, and every resolved path
is checked to stay inside its root (see :func:`safe_join`).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def repo_root() -> Path:
    return _REPO_ROOT


def data_root() -> Path:
    root = os.environ.get("FLYMIND_DATA_DIR")
    return Path(root).expanduser().resolve() if root else (_REPO_ROOT / "data").resolve()


def raw_dir() -> Path:
    return data_root() / "raw"


def processed_dir() -> Path:
    return data_root() / "processed"


def cache_dir() -> Path:
    return data_root() / "cache"


def fixtures_dir() -> Path:
    return data_root() / "fixtures"


def experiments_dir() -> Path:
    root = os.environ.get("FLYMIND_EXPERIMENTS_DIR")
    return Path(root).expanduser().resolve() if root else (_REPO_ROOT / "experiments").resolve()


def validate_identifier(value: str, kind: str = "identifier") -> str:
    """Reject identifiers that could be used for path traversal or injection."""
    if not isinstance(value, str) or not _ID_RE.match(value) or ".." in value:
        raise ValueError(f"invalid {kind}: {value!r}")
    return value


def safe_join(root: Path, *parts: str) -> Path:
    """Join ``parts`` onto ``root`` and refuse results that escape ``root``."""
    root = root.resolve()
    candidate = root.joinpath(*parts).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("path escapes its root directory")
    return candidate
