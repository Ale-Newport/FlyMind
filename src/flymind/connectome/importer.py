"""High-level import: detect files, choose the adapter, build, validate."""

from __future__ import annotations

from pathlib import Path

from flymind.common.paths import processed_dir
from flymind.connectome.adapters import ADAPTERS, DatasetAdapter
from flymind.connectome.detect import DetectedFile, scan_directory
from flymind.connectome.sources import BUNDLES, bundle_dir, fetch_bundle
from flymind.connectome.store import clear_store_cache


def choose_adapter(files: list[DetectedFile], dataset_id: str | None = None) -> DatasetAdapter:
    if dataset_id:
        for ad in ADAPTERS:
            if ad.info.dataset_id == dataset_id:
                return ad
        raise ValueError(f"no adapter for dataset id {dataset_id!r}")
    roles = {f.role for f in files}
    # The v630 reproduction set has only Shiu files; v783 needs a v783 neuron list.
    v783 = ADAPTERS[0]
    if any(r in roles for r in v783.info.required_roles):
        return v783
    if "shiu_completeness" in roles:
        raise ValueError(
            "only Shiu et al. files found: pass --dataset flywire_fafb_630_shiu for the v630 "
            "reproduction set, or add a v783 neuron list (proofread_root_ids_783.npy, Codex "
            "neurons/classification or the annotations TSV)"
        )
    raise ValueError("no supported dataset files recognised")


def import_directory(
    directory: Path,
    dataset_id: str | None = None,
    connectivity: str = "auto",
    out_root: Path | None = None,
) -> Path:
    files = scan_directory(directory)
    files = [f for f in files if f.role != "codex_labels"]  # personal data, never imported
    adapter = choose_adapter(files, dataset_id)
    out = adapter.build(files, out_root or processed_dir(), connectivity=connectivity)
    clear_store_cache()
    return out


def fetch_and_import(bundle_key: str, out_root: Path | None = None, progress=None) -> Path:
    fetch_bundle(bundle_key, progress=progress)
    return import_directory(
        bundle_dir(bundle_key), BUNDLES[bundle_key].dataset_id, out_root=out_root
    )
