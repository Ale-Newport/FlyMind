"""Software/machine provenance captured with every dataset import and experiment."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from flymind import __version__
from flymind.common.paths import repo_root

_TRACKED_PACKAGES = (
    "numpy",
    "scipy",
    "pandas",
    "pyarrow",
    "duckdb",
    "brian2",
    "numba",
    "mujoco",
    "flygym",
    "fastapi",
    "torch",
)


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root(), capture_output=True, text=True, timeout=5
        )
        sha = out.stdout.strip()
        if not sha:
            return None
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],  # untracked (non-ignored) files count as dirty
            cwd=repo_root(),
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return None


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {"flymind": __version__}
    for name in _TRACKED_PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def machine_info() -> dict[str, object]:
    info: dict[str, object] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }
    try:
        if platform.system() == "Darwin":
            info["cpu_model"] = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            info["memory_bytes"] = int(
                subprocess.run(
                    ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
                ).stdout.strip()
            )
        elif Path("/proc/meminfo").exists():
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal"):
                    info["memory_bytes"] = int(line.split()[1]) * 1024
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    info["cpu_model"] = line.split(":", 1)[1].strip()
                    break
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return info


def runtime_provenance() -> dict[str, object]:
    return {
        "flymind_version": __version__,
        "git_commit": git_commit(),
        "packages": package_versions(),
        "machine": machine_info(),
        "timestamp": utc_now(),
    }


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
