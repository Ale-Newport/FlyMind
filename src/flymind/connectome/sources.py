"""Registry of public, openly downloadable data sources (pinned and checksummed).

Only sources that are reachable without signing in are fetched automatically.
FlyWire Codex downloads require a Google sign-in and acceptance of the FlyWire
terms, so FlyMind never fetches them: users download Codex files themselves and
run ``flymind data import <dir>`` (files are recognised by their headers).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from flymind.common.logging import get_logger
from flymind.common.paths import raw_dir

log = get_logger("connectome.sources")

SHIU_COMMIT = "91bdd1e7dcf193f3e7ca5a8933497fcef63b7960"
ANNOTATIONS_COMMIT = "c294fba426f5abe861289bdc1171188026646b04"
_SHIU_RAW = f"https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/{SHIU_COMMIT}"
_ANN_RAW = (
    f"https://raw.githubusercontent.com/flyconnectome/flywire_annotations/{ANNOTATIONS_COMMIT}"
)
_ZENODO_CONN = "https://zenodo.org/records/10676866/files"

FLYWIRE_LICENSE_NOTE = (
    "FlyWire public release data: CC BY-NC 4.0 per https://flywire.ai/guidelines "
    "(the Zenodo deposits 10.5281/zenodo.10676866 and 10.5281/zenodo.10877326 are "
    "labelled CC BY 4.0). FlyMind does not redistribute these files."
)


@dataclass(frozen=True)
class RemoteFile:
    name: str
    url: str
    sha256: str | None
    size_bytes: int | None
    role: str
    license: str
    note: str = ""


@dataclass(frozen=True)
class SourceBundle:
    key: str
    title: str
    dataset_id: str
    description: str
    files: list[RemoteFile] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)


BUNDLES: dict[str, SourceBundle] = {
    "flywire-783-open": SourceBundle(
        key="flywire-783-open",
        title="FlyWire FAFB v783 (open, no sign-in)",
        dataset_id="flywire_fafb_783",
        description=(
            "Full proofread FlyWire v783 neuron list (Zenodo), the Shiu et al. 2024 "
            "connectivity table for v783 (15.09M connections, 54.5M synapses, signed by "
            "predicted transmitter), FlyWire community annotations (cell types, classes, "
            "positions) and per-neuron output-neuropil synapse counts."
        ),
        files=[
            RemoteFile(
                "proofread_root_ids_783.npy",
                f"{_ZENODO_CONN}/proofread_root_ids_783.npy?download=1",
                "7c7b7e818e9232e5ab64793d52ba20574dbe9da3a6509fbc74193b0f259a01be",
                1114168,
                "zenodo_root_ids",
                "CC BY 4.0 (Zenodo 10.5281/zenodo.10676866)",
            ),
            RemoteFile(
                "Completeness_783.csv",
                f"{_SHIU_RAW}/Completeness_783.csv",
                "bbb847a4cc2caaa7a16349722d220c087317b946d148d4d592d94d250617a311",
                3327347,
                "shiu_completeness",
                "FlyWire data (see note); repository code MIT",
            ),
            RemoteFile(
                "Connectivity_783.parquet",
                f"{_SHIU_RAW}/Connectivity_783.parquet",
                "efeb23fb99098e9c390f6869969b2a121a2ee92c833cfc45ecb2c1d8e1af0347",
                100804642,
                "shiu_connectivity",
                "FlyWire data (see note); repository code MIT",
            ),
            RemoteFile(
                "Supplemental_file1_neuron_annotations.tsv",
                f"{_ANN_RAW}/supplemental_files/Supplemental_file1_neuron_annotations.tsv",
                "30be6c73975a70c56d930e27911f36455d3886e15abf383b78edd2a5d679e0b6",
                27015208,
                "annotations_tsv",
                "FlyWire data (repository has no explicit license; see note)",
                note="Pinned to the last revision whose root IDs match v783 exactly.",
            ),
            RemoteFile(
                "per_neuron_neuropil_count_pre_783.feather",
                f"{_ZENODO_CONN}/per_neuron_neuropil_count_pre_783.feather?download=1",
                "35442a46f076892dff91bd6e55fa1489b3acc64fda1d35cee7dbbbbc509a3dff",
                16853770,
                "zenodo_neuropil_pre",
                "CC BY 4.0 (Zenodo 10.5281/zenodo.10676866)",
            ),
        ],
        citations=[
            "Dorkenwald S. et al. (2024) Neuronal wiring diagram of an adult brain. Nature 634, "
            "124-138. doi:10.1038/s41586-024-07558-y",
            "Schlegel P. et al. (2024) Whole-brain annotation and multi-connectome cell typing of "
            "Drosophila. Nature 634, 139-152. doi:10.1038/s41586-024-07686-5",
            "Eckstein N., Bates A.S. et al. (2024) Neurotransmitter classification from electron "
            "microscopy images at synaptic sites in Drosophila melanogaster. Cell 187, 2574-2594. "
            "doi:10.1016/j.cell.2024.03.016",
            "Shiu P.K. et al. (2024) A Drosophila computational brain model reveals sensorimotor "
            "processing. Nature 634, 210-219. doi:10.1038/s41586-024-07763-9",
            "Zheng Z. et al. (2018) A complete electron microscopy volume of the brain of adult "
            "Drosophila melanogaster. Cell 174, 730-743. doi:10.1016/j.cell.2018.06.019",
            "Buhmann J. et al. (2021) Automatic detection of synaptic partners in a whole-brain "
            "Drosophila electron microscopy data set. Nat Methods 18, 771-774. "
            "doi:10.1038/s41592-021-01183-7",
        ],
    ),
    "flywire-783-skeletons": SourceBundle(
        key="flywire-783-skeletons",
        title="FlyWire v783 neuron skeletons (opt-in, 5.4 GB)",
        dataset_id="flywire_fafb_783",
        description=(
            "Healed, downsampled L2 skeletons of all proofread v783 neurons (Schlegel et al. 2024 "
            "supplement, Zenodo 10.5281/zenodo.10877326), coordinates in nm. Re-chunked locally "
            "into a per-neuron index for the 3D explorer."
        ),
        files=[
            RemoteFile(
                "sk_lod1_783_healed_ds2.parquet",
                "https://zenodo.org/records/10877326/files/sk_lod1_783_healed_ds2.parquet?download=1",
                "c83e95a672f466cead5c3bc3e295280a6003e6d63ec6c777e53603c056feb6a8",
                5355543468,
                "skeletons_parquet",
                "CC BY 4.0 (Zenodo 10.5281/zenodo.10877326)",
            ),
        ],
        citations=[
            "Schlegel P. et al. (2024) Whole-brain annotation and multi-connectome cell typing of "
            "Drosophila. Nature 634, 139-152. doi:10.1038/s41586-024-07686-5",
            "Dorkenwald S. et al. (2024) Neuronal wiring diagram of an adult brain. Nature 634, "
            "124-138. doi:10.1038/s41586-024-07558-y",
        ],
    ),
    "flywire-630-shiu": SourceBundle(
        key="flywire-630-shiu",
        title="FlyWire FAFB v630 as used by Shiu et al. 2024 (reproduction only)",
        dataset_id="flywire_fafb_630_shiu",
        description=(
            "The exact v630 neuron list and connectivity used for the published Shiu et al. "
            "figures. Used only to reproduce published results; no annotations."
        ),
        files=[
            RemoteFile(
                "2023_03_23_completeness_630_final.csv",
                f"{_SHIU_RAW}/2023_03_23_completeness_630_final.csv",
                "e6b71e17671a9bdb05f55e4bc6774640a1418cb7a05125e0fc994ad40f9bfdfb",
                3057611,
                "shiu_completeness",
                "FlyWire data (see note); repository code MIT",
            ),
            RemoteFile(
                "2023_03_23_connectivity_630_final.parquet",
                f"{_SHIU_RAW}/2023_03_23_connectivity_630_final.parquet",
                "94db8c650533bc36ffa3223f2e62325d5648b8d6bd31c3a4e1c804628c7557b3",
                86630944,
                "shiu_connectivity",
                "FlyWire data (see note); repository code MIT",
            ),
        ],
        citations=[
            "Shiu P.K. et al. (2024) A Drosophila computational brain model reveals sensorimotor "
            "processing. Nature 634, 210-219. doi:10.1038/s41586-024-07763-9",
            "Dorkenwald S. et al. (2024) Neuronal wiring diagram of an adult brain. Nature 634, "
            "124-138. doi:10.1038/s41586-024-07558-y",
        ],
    ),
}


def bundle_dir(key: str) -> Path:
    return raw_dir() / key


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def fetch_bundle(
    key: str, dest: Path | None = None, progress=None
) -> list[tuple[RemoteFile, Path, str]]:
    """Download (or reuse) every file of a bundle and verify pinned checksums.

    Returns (file, local path, sha256) triples. Files without a pinned checksum are
    hashed and the digest is recorded in the dataset manifest at import.
    """
    bundle = BUNDLES[key]
    dest = dest or bundle_dir(key)
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, read=300.0)) as client:
        for rf in bundle.files:
            path = dest / rf.name
            if path.exists() and (rf.sha256 is None or _sha256(path) == rf.sha256):
                digest = _sha256(path)
                out.append((rf, path, digest))
                if progress:
                    progress(f"cached  {rf.name}")
                continue
            tmp = path.with_suffix(path.suffix + ".part")
            if progress:
                progress(f"fetch   {rf.name}  <- {rf.url.split('?')[0]}")
            with client.stream("GET", rf.url) as resp:
                resp.raise_for_status()
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_bytes(1 << 20):
                        fh.write(chunk)
            digest = _sha256(tmp)
            if rf.sha256 is not None and digest != rf.sha256:
                tmp.unlink(missing_ok=True)
                raise ValueError(f"checksum mismatch for {rf.name}: {digest} != {rf.sha256}")
            tmp.replace(path)
            out.append((rf, path, digest))
    return out
