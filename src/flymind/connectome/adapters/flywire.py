"""FlyWire FAFB adapters (v783 full brain; v630 Shiu reproduction set)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.feather as pf
import pyarrow.parquet as pq

from flymind.common.logging import get_logger
from flymind.common.provenance import runtime_provenance, sha256_file, utc_now
from flymind.connectome.adapters.base import AdapterInfo, DatasetAdapter
from flymind.connectome.detect import DetectedFile
from flymind.connectome.manifest import Citation, DatasetManifest, SourceFile
from flymind.connectome.sources import BUNDLES, FLYWIRE_LICENSE_NOTE
from flymind.connectome.store import write_dataset
from flymind.connectome.validate import validate_and_record

log = get_logger("connectome.flywire")

# Shiu et al. (2024) sign convention, also verified on Connectivity_783 by
# kornel77777/fly-brain-sim tests: GABA and glutamate inhibitory, everything else
# (acetylcholine and the monoamines) excitatory.
FLYWIRE_SIGN_POLICY = {"ACH": 1, "GABA": -1, "GLUT": -1, "DA": 1, "SER": 1, "OCT": 1, "UNKNOWN": 1}
_NT_NAMES = {
    "acetylcholine": "ACH",
    "gaba": "GABA",
    "glutamate": "GLUT",
    "dopamine": "DA",
    "serotonin": "SER",
    "octopamine": "OCT",
    "histamine": "HIST",
}
VOXEL_NM = np.array([4.0, 4.0, 40.0])  # annotation TSV positions are 4x4x40 nm voxels


def _ids(series: pd.Series) -> np.ndarray:
    """Parse identifier strings to int64 without passing through float."""
    s = series.astype("string").str.strip()
    if s.isna().any():
        raise ValueError(f"{int(s.isna().sum())} missing identifiers")
    if not s.str.fullmatch(r"-?\d+").all():
        bad = s[~s.str.fullmatch(r"-?\d+")].head(3).tolist()
        raise ValueError(f"non-integer identifiers (possible float corruption): {bad}")
    return np.array(s.tolist(), dtype=np.int64)


def _norm_nt(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)) or value == "":
        return "UNKNOWN"
    v = str(value).strip()
    return _NT_NAMES.get(v.lower(), v.upper())


def _read_csv(path: Path, **kw) -> pd.DataFrame:
    sep = "\t" if path.suffix.lower() in (".tsv",) or path.name.endswith(".tsv.gz") else ","
    return pd.read_csv(path, sep=sep, dtype=str, keep_default_na=True, encoding="utf-8-sig", **kw)


class _FlyWireBase(DatasetAdapter):
    version: str = ""

    def _source_files(self, files: list[DetectedFile]) -> list[SourceFile]:
        urls = {rf.name: rf.url.split("?")[0] for b in BUNDLES.values() for rf in b.files}
        return [
            SourceFile(
                name=f.path.name,
                role=f.role,
                sha256=sha256_file(f.path),
                size_bytes=f.path.stat().st_size,
                detected_format=f.format,
                url=urls.get(f.path.name),
            )
            for f in files
        ]

    @staticmethod
    def _shiu_edges(path: Path, root_sorted: np.ndarray) -> tuple[pd.DataFrame, dict]:
        t = pq.read_table(
            path, columns=["Presynaptic_ID", "Postsynaptic_ID", "Connectivity", "Excitatory"]
        )
        pre_id = t["Presynaptic_ID"].to_numpy().astype(np.int64)
        post_id = t["Postsynaptic_ID"].to_numpy().astype(np.int64)
        pre = np.searchsorted(root_sorted, pre_id)
        post = np.searchsorted(root_sorted, post_id)
        ok = (pre < len(root_sorted)) & (post < len(root_sorted))
        ok &= root_sorted[np.minimum(pre, len(root_sorted) - 1)] == pre_id
        ok &= root_sorted[np.minimum(post, len(root_sorted) - 1)] == post_id
        if not ok.all():
            raise ValueError(
                f"{int((~ok).sum())} Shiu connections reference neurons outside the dataset's "
                "neuron set (wrong version or specimen?)"
            )
        sign = t["Excitatory"].to_numpy().astype(np.int8)
        if not np.isin(sign, (-1, 1)).all():
            raise ValueError("Shiu 'Excitatory' column contains values other than +-1")
        edges = pd.DataFrame(
            {
                "pre_idx": pre.astype(np.int32),
                "post_idx": post.astype(np.int32),
                "syn_count": t["Connectivity"].to_numpy().astype(np.int32),
                "sign": sign,
            }
        )
        n_dup = int(edges.duplicated(["pre_idx", "post_idx"]).sum())
        if n_dup:
            raise ValueError(f"Shiu connectivity has {n_dup} duplicated pairs")
        stats = {"source_rows": len(edges), "min_syn_count": int(edges["syn_count"].min())}
        return edges, stats


class FlyWireFAFB783Adapter(_FlyWireBase):
    version = "783"
    info = AdapterInfo(
        name="FlyWireFAFB783Adapter",
        dataset_id="flywire_fafb_783",
        title="FlyWire FAFB v783 (adult female brain)",
        specimen="FAFB (Full Adult Fly Brain), adult female D. melanogaster; FlyWire release 783",
        status="supported",
        description="Full-brain FlyWire v783 from open sources and/or user-downloaded Codex files.",
        required_roles=(
            "zenodo_root_ids",
            "codex_neurons",
            "codex_classification",
            "annotations_tsv",
        ),
        optional_roles=(
            "shiu_connectivity",
            "shiu_completeness",
            "codex_connections",
            "codex_cell_types",
            "codex_coordinates",
            "codex_names",
            "zenodo_neuropil_pre",
            "codex_classification_types",
        ),
    )

    def build(
        self, files: list[DetectedFile], out_root: Path, connectivity: str = "auto", **options
    ) -> Path:
        by_role: dict[str, Path] = {}
        for f in files:
            if f.role in by_role:
                raise ValueError(f"two files provide {f.role}: {by_role[f.role]} and {f.path}")
            by_role[f.role] = f.path
        transformations: list[str] = []
        notes: list[str] = []

        # 1. Canonical neuron set ------------------------------------------------
        if "zenodo_root_ids" in by_role:
            raw = np.load(by_role["zenodo_root_ids"], allow_pickle=False)
            if raw.dtype.kind not in "iu" or (raw.dtype.kind == "u" and raw.max() >= 2**63):
                raise ValueError("unexpected dtype/range in proofread_root_ids array")
            root = np.sort(raw.astype(np.int64))
            id_source = "proofread_root_ids_783.npy (Zenodo)"
        else:
            for role in ("codex_neurons", "codex_classification", "annotations_tsv"):
                if role in by_role:
                    root = np.sort(_ids(_read_csv(by_role[role], usecols=["root_id"])["root_id"]))
                    id_source = role
                    break
            else:
                raise ValueError(
                    "no neuron list found (need proofread_root_ids, Codex "
                    "neurons/classification, or the annotations TSV)"
                )
        if len(np.unique(root)) != len(root):
            raise ValueError("duplicate root ids in the neuron list")
        n = len(root)
        neurons = pd.DataFrame({"idx": np.arange(n, dtype=np.int32), "root_id": root})
        transformations.append(f"neuron set from {id_source}; sorted by root_id; dense idx")

        def attach(df: pd.DataFrame, label: str) -> pd.DataFrame:
            ids = _ids(df["root_id"])
            pos = np.searchsorted(root, ids)
            found = (pos < n) & (root[np.minimum(pos, n - 1)] == ids)
            if not found.all():
                raise ValueError(
                    f"{label}: {int((~found).sum())} root ids not in the v{self.version}"
                    " neuron set (different release or specimen?)"
                )
            df = df.copy()
            df["idx"] = pos
            return df.drop_duplicates("idx").set_index("idx")

        def put(col: str, values: pd.Series, label: str) -> None:
            if col not in neurons:
                neurons[col] = pd.Series([None] * n, dtype="object")
            neurons.loc[values.index, col] = values.values
            transformations.append(f"{col} <- {label}")

        # 2. Annotations (Schlegel et al. 2024) -----------------------------------
        if "annotations_tsv" in by_role:
            ann = attach(_read_csv(by_role["annotations_tsv"]), "annotations")
            for col in (
                "flow",
                "super_class",
                "cell_class",
                "cell_sub_class",
                "side",
                "hemibrain_type",
            ):
                put(col, ann[col], f"annotations.{col}")
            consolidated = ann["cell_type"].where(ann["cell_type"].notna(), ann["hemibrain_type"])
            put("cell_type", consolidated, "annotations.cell_type, else hemibrain_type")
            put("nt_type", ann["top_nt"].map(_norm_nt), "annotations.top_nt (normalised)")
            put(
                "nt_confidence",
                pd.to_numeric(ann["top_nt_conf"], errors="coerce"),
                "annotations.top_nt_conf",
            )
            xyz = ann[["pos_x", "pos_y", "pos_z"]].apply(pd.to_numeric, errors="coerce")
            xyz = xyz.to_numpy() * VOXEL_NM
            for k, c in enumerate(("pos_x", "pos_y", "pos_z")):
                put(
                    c,
                    pd.Series(xyz[:, k], index=ann.index),
                    f"annotations.{c} x {VOXEL_NM[k]:g} nm",
                )

        # 3. Codex files override where present ----------------------------------
        if "codex_classification" in by_role:
            cl = attach(_read_csv(by_role["codex_classification"]), "codex classification")
            for src, dst in (
                ("flow", "flow"),
                ("super_class", "super_class"),
                ("class", "cell_class"),
                ("sub_class", "cell_sub_class"),
                ("side", "side"),
            ):
                put(dst, cl[src], f"codex classification.{src}")
        if "codex_cell_types" in by_role:
            ct = attach(_read_csv(by_role["codex_cell_types"]), "codex cell types")
            put("cell_type", ct["primary_type"], "codex consolidated_cell_types.primary_type")
        if "codex_neurons" in by_role:
            nr = attach(_read_csv(by_role["codex_neurons"]), "codex neurons")
            put("nt_type", nr["nt_type"].map(_norm_nt), "codex neurons.nt_type")
            put(
                "nt_confidence",
                pd.to_numeric(nr["nt_type_score"], errors="coerce"),
                "codex neurons.nt_type_score",
            )
        if "codex_names" in by_role:
            nm = attach(_read_csv(by_role["codex_names"]), "codex names")
            put("name", nm["name"], "codex names.name")
        if "codex_coordinates" in by_role:
            co = attach(_read_csv(by_role["codex_coordinates"]), "codex coordinates")
            xyz = co["position"].str.strip("[]").str.split(expand=True).astype(float).to_numpy()
            for k, c in enumerate(("pos_x", "pos_y", "pos_z")):
                put(c, pd.Series(xyz[:, k], index=co.index), f"codex coordinates.position[{k}] nm")

        # 4. Primary neuropil -------------------------------------------------------
        conn_table: pa.Table | None = None
        if "codex_connections" in by_role:
            cc = _read_csv(by_role["codex_connections"])
            cc_pre, cc_post = _ids(cc["pre_root_id"]), _ids(cc["post_root_id"])
            conn_table = pa.table(
                {
                    "pre_root_id": cc_pre,
                    "post_root_id": cc_post,
                    "neuropil": cc["neuropil"].astype("string"),
                    "syn_count": cc["syn_count"].astype(np.int32),
                    "nt_type": cc["nt_type"].map(_norm_nt),
                }
            )
            per = (
                pd.concat(
                    [
                        pd.DataFrame(
                            {
                                "root_id": cc_pre,
                                "neuropil": cc["neuropil"],
                                "n": cc["syn_count"].astype(np.int64),
                            }
                        ),
                        pd.DataFrame(
                            {
                                "root_id": cc_post,
                                "neuropil": cc["neuropil"],
                                "n": cc["syn_count"].astype(np.int64),
                            }
                        ),
                    ]
                )
                .groupby(["root_id", "neuropil"], as_index=False)["n"]
                .sum()
            )
            per = per[~per["neuropil"].isin(["None", "UNASGD", ""])]
            best = per.sort_values("n", ascending=False).drop_duplicates("root_id")
            put(
                "primary_neuropil",
                attach(best.astype({"root_id": str}), "neuropil")["neuropil"],
                "argmax neuropil by synapses (codex connections, in+out)",
            )
        elif "zenodo_neuropil_pre" in by_role:
            npre = pf.read_table(by_role["zenodo_neuropil_pre"]).to_pandas()
            # "None"/"UNASGD" mark synapses outside any annotated neuropil
            npre = npre[npre["neuropil"].notna() & ~npre["neuropil"].isin(["None", "UNASGD", ""])]
            # This table covers every segment, including unproofread fragments; keep rows
            # for proofread neurons only (an explicit, recorded filter, not an ID merge).
            member = np.isin(npre["pre_pt_root_id"].to_numpy(dtype=np.int64), root)
            transformations.append(
                f"neuropil pre counts: dropped {int((~member).sum())} rows of non-proofread "
                "segments"
            )
            npre = npre[member]
            best = npre.sort_values("count", ascending=False).drop_duplicates("pre_pt_root_id")
            best = best.rename(columns={"pre_pt_root_id": "root_id"})
            best["root_id"] = best["root_id"].astype(str)
            put(
                "primary_neuropil",
                attach(best, "neuropil pre counts")["neuropil"],
                "argmax neuropil by presynapse count (Zenodo per_neuron_neuropil_count_pre_783)",
            )
            notes.append(
                "primary_neuropil is defined by output synapses; neurons without "
                "presynapses in the brain have none"
            )

        # 5. Connectivity ------------------------------------------------------------
        if connectivity == "auto":
            connectivity = "shiu" if "shiu_connectivity" in by_role else "codex"
        filters: dict[str, object] = {"connectivity_source": connectivity}
        if connectivity == "shiu":
            if "shiu_connectivity" not in by_role:
                raise ValueError("connectivity=shiu needs Connectivity_783.parquet")
            edges, stats = self._shiu_edges(by_role["shiu_connectivity"], root)
            n_source = stats["source_rows"]
            filters.update(synapse_threshold=None, min_syn_count=stats["min_syn_count"])
            sign_policy_source = (
                "Shiu et al. 2024 Connectivity_783 'Excitatory' column (per presynaptic neuron; "
                "GABA/glutamate -> -1, others +1), preserved verbatim"
            )
            transformations.append(
                "edges <- Shiu Connectivity_783 (IDs re-indexed to this "
                "dataset's idx; Shiu's own index columns ignored)"
            )
            if "shiu_completeness" in by_role:
                comp = _ids(_read_csv(by_role["shiu_completeness"]).iloc[:, 0])
                missing = np.setdiff1d(root, comp)
                notes.append(
                    f"{len(missing)} v783 neurons are absent from the Shiu neuron list "
                    "and therefore have no connections in this connectivity source"
                )
        elif connectivity == "codex":
            if conn_table is None:
                raise ValueError("connectivity=codex needs a Codex connections file")
            agg = (
                conn_table.group_by(["pre_root_id", "post_root_id"])
                .aggregate([("syn_count", "sum")])
                .to_pandas()
            )
            pre = np.searchsorted(root, agg["pre_root_id"].to_numpy())
            post = np.searchsorted(root, agg["post_root_id"].to_numpy())
            nt = (
                neurons["nt_type"].fillna("UNKNOWN").to_numpy()
                if "nt_type" in neurons
                else (np.array(["UNKNOWN"] * n))
            )
            sign = np.array([FLYWIRE_SIGN_POLICY.get(x, 1) for x in nt], dtype=np.int8)[pre]
            edges = pd.DataFrame(
                {
                    "pre_idx": pre.astype(np.int32),
                    "post_idx": post.astype(np.int32),
                    "syn_count": agg["syn_count_sum"].astype(np.int32),
                    "sign": sign,
                }
            )
            n_source = conn_table.num_rows
            filters.update(
                synapse_threshold="as provided by Codex (pair total >= 5 for connections.csv)"
            )
            sign_policy_source = "FlyMind FLYWIRE_SIGN_POLICY applied to presynaptic nt_type"
            transformations.append("edges <- Codex connections aggregated over neuropils")
        else:
            raise ValueError("connectivity must be auto, shiu or codex")

        out = neurons.reindex(
            columns=["idx", "root_id"] + [c for c in neurons.columns if c not in ("idx", "root_id")]
        )
        out["output_synapses"] = np.bincount(
            edges["pre_idx"], weights=edges["syn_count"], minlength=n
        ).astype(np.int64)
        out["input_synapses"] = np.bincount(
            edges["post_idx"], weights=edges["syn_count"], minlength=n
        ).astype(np.int64)
        bundle = BUNDLES["flywire-783-open"]
        manifest = DatasetManifest(
            dataset_id=self.info.dataset_id,
            dataset_name="FlyWire FAFB",
            dataset_version="783",
            specimen=self.info.specimen,
            adapter=self.info.name,
            source="FlyWire Consortium public release 783 (see files and citations)",
            source_urls=sorted({s.url for s in self._source_files(files) if s.url}),
            license=FLYWIRE_LICENSE_NOTE,
            citations=[Citation(text=c) for c in bundle.citations],
            imported_at=utc_now(),
            files=self._source_files(files),
            transformations=transformations,
            filters=filters,
            sign_policy=FLYWIRE_SIGN_POLICY,
            sign_policy_source=sign_policy_source,
            n_neurons=n,
            n_source_connections=int(n_source),
            n_edges=len(edges),
            n_synapses=int(edges["syn_count"].sum()),
            processing=runtime_provenance(),
            notes=notes,
        )
        out_dir = out_root / self.info.dataset_id
        write_dataset(out_dir, out, edges, manifest, connections=conn_table)
        validate_and_record(out_dir)
        return out_dir


class FlyWireFAFB630ShiuAdapter(_FlyWireBase):
    """The exact v630 network of Shiu et al. 2024 (neuron list + signed connectivity only)."""

    version = "630"
    info = AdapterInfo(
        name="FlyWireFAFB630ShiuAdapter",
        dataset_id="flywire_fafb_630_shiu",
        title="FlyWire FAFB v630 (Shiu et al. 2024 network; reproduction only)",
        specimen="FAFB adult female; FlyWire release 630 as distributed with Shiu et al. 2024",
        status="supported",
        description="Used to reproduce published Shiu et al. results with identical inputs.",
        required_roles=("shiu_completeness",),
        optional_roles=("shiu_connectivity",),
    )

    def build(self, files: list[DetectedFile], out_root: Path, **options) -> Path:
        by_role = {f.role: f.path for f in files}
        comp = _read_csv(by_role["shiu_completeness"])
        root = _ids(comp.iloc[:, 0])
        if not (np.diff(root) > 0).all():
            raise ValueError("Shiu completeness IDs are expected sorted ascending")
        n = len(root)
        edges, stats = self._shiu_edges(by_role["shiu_connectivity"], root)
        neurons = pd.DataFrame({"idx": np.arange(n, dtype=np.int32), "root_id": root})
        neurons["output_synapses"] = np.bincount(
            edges["pre_idx"], weights=edges["syn_count"], minlength=n
        ).astype(np.int64)
        neurons["input_synapses"] = np.bincount(
            edges["post_idx"], weights=edges["syn_count"], minlength=n
        ).astype(np.int64)
        bundle = BUNDLES["flywire-630-shiu"]
        manifest = DatasetManifest(
            dataset_id=self.info.dataset_id,
            dataset_name="FlyWire FAFB (Shiu et al. 2024 v630)",
            dataset_version="630",
            specimen=self.info.specimen,
            adapter=self.info.name,
            source="philshiu/Drosophila_brain_model @ " + "91bdd1e7",
            source_urls=sorted({s.url for s in self._source_files(files) if s.url}),
            license=FLYWIRE_LICENSE_NOTE,
            citations=[Citation(text=c) for c in bundle.citations],
            imported_at=utc_now(),
            files=self._source_files(files),
            transformations=[
                "neuron order identical to Shiu completeness file (sorted root_id)",
                "edges re-indexed by root_id lookup",
            ],
            filters={"connectivity_source": "shiu", "min_syn_count": stats["min_syn_count"]},
            sign_policy=FLYWIRE_SIGN_POLICY,
            sign_policy_source="Shiu et al. 2024 'Excitatory' column, preserved verbatim",
            n_neurons=n,
            n_source_connections=stats["source_rows"],
            n_edges=len(edges),
            n_synapses=int(edges["syn_count"].sum()),
            processing=runtime_provenance(),
            notes=["No cell annotations: used only for reproducing published results by ID."],
        )
        out_dir = out_root / self.info.dataset_id
        write_dataset(out_dir, neurons, edges, manifest)
        validate_and_record(out_dir)
        return out_dir
