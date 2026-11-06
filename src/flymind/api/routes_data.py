"""Dataset, neuron, connectivity and geometry endpoints."""

from __future__ import annotations

import io
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from flymind.api.common import neuron_record, parse_root_ids, store_or_404
from flymind.brain.params import PARAMETER_INFO, LIFParams
from flymind.common.evidence import EVIDENCE_DESCRIPTIONS
from flymind.connectome.adapters import ADAPTERS
from flymind.connectome.selectors import NeuronSelector, load_groups, resolve, save_group
from flymind.connectome.sources import BUNDLES, FLYWIRE_LICENSE_NOTE
from flymind.connectome.store import list_datasets
from flymind.visualization import geometry

router = APIRouter(prefix="/api")

CLI_ALIASES = {
    "flywire-783-open": "flywire-783",
    "flywire-630-shiu": "flywire-630",
    "flywire-783-skeletons": "skeletons",
}
CODEX_URL = "https://codex.flywire.ai/app/cell_details?cell_names_or_id={rid}&data_version={v}"


@router.get("/datasets")
def datasets():
    out = []
    for m in list_datasets():
        out.append(
            {
                "dataset_id": m.dataset_id,
                "name": m.dataset_name,
                "version": m.dataset_version,
                "specimen": m.specimen,
                "synthetic": m.synthetic,
                "n_neurons": m.n_neurons,
                "n_edges": m.n_edges,
                "n_synapses": m.n_synapses,
                "license": m.license,
                "validation_status": m.validation_status,
                "imported_at": m.imported_at,
                "adapter": m.adapter,
                "has_skeletons": m.dataset_id == geometry.SKELETON_DATASET
                and (geometry.skeleton_store_dir() / "skeleton_index.npz").is_file(),
            }
        )
    return out


@router.get("/datasets/{dataset_id}")
def dataset(dataset_id: str):
    store = store_or_404(dataset_id)
    return store.manifest.model_dump()


@router.get("/datasets/{dataset_id}/validation")
def validation(dataset_id: str):
    import json

    store = store_or_404(dataset_id)
    path = store.directory / "validation_report.json"
    if not path.is_file():
        raise HTTPException(404, "validation report not found; run flymind data validate")
    return json.loads(path.read_text())


@router.get("/sources")
def sources():
    return {
        "bundles": [
            {
                "key": b.key,
                "title": b.title,
                "dataset_id": b.dataset_id,
                "description": b.description,
                "citations": b.citations,
                "files": [
                    {
                        "name": f.name,
                        "url": f.url.split("?")[0],
                        "sha256": f.sha256,
                        "size_bytes": f.size_bytes,
                        "license": f.license,
                    }
                    for f in b.files
                ],
                "command": f"uv run flymind data fetch {CLI_ALIASES.get(b.key, b.key)}",
            }
            for b in BUNDLES.values()
        ],
        "adapters": [
            {
                "name": a.info.name,
                "dataset_id": a.info.dataset_id,
                "title": a.info.title,
                "status": a.info.status,
                "description": a.info.description,
                "specimen": a.info.specimen,
            }
            for a in ADAPTERS
        ],
        "codex": {
            "url": "https://codex.flywire.ai/api/download",
            "note": "Codex downloads require signing in and accepting the FlyWire terms; FlyMind "
            "never fetches them. Download files manually, then run "
            "`uv run flymind data import <folder>` (files are recognised by header).",
        },
        "license_note": FLYWIRE_LICENSE_NOTE,
    }


@router.get("/evidence")
def evidence():
    return {k.value: v for k, v in EVIDENCE_DESCRIPTIONS.items()}


@router.get("/brain/params")
def params():
    return {
        "defaults": LIFParams().model_dump(),
        "info": {k: v.model_dump() for k, v in PARAMETER_INFO.items()},
    }


# ------------------------------------------------------------------ neurons
@router.get("/datasets/{dataset_id}/neurons")
def search_neurons(
    dataset_id: str,
    q: str | None = Query(None, max_length=200),
    super_class: str | None = None,
    cell_type: str | None = None,
    side: str | None = None,
    nt_type: str | None = None,
    neuropil: str | None = None,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    store = store_or_404(dataset_id)
    nb = store.neurons
    mask = np.ones(len(nb), dtype=bool)
    if q:
        q = q.strip()
        if q.isdigit():
            mask &= (nb["root_id"].astype(str).str.startswith(q)).to_numpy()
        else:
            ql = q.lower()
            m = np.zeros(len(nb), dtype=bool)
            for col in ("cell_type", "hemibrain_type", "name", "cell_class"):
                if col in nb:
                    m |= nb[col].fillna("").str.lower().str.contains(ql, regex=False).to_numpy()
            mask &= m
    for col, val in (
        ("super_class", super_class),
        ("cell_type", cell_type),
        ("side", side),
        ("nt_type", nt_type),
        ("primary_neuropil", neuropil),
    ):
        if val:
            mask &= (nb[col] == val).to_numpy()
    hits = np.nonzero(mask)[0]
    if q and not q.isdigit():
        # exact cell-type matches first
        exact = (nb["cell_type"].iloc[hits].fillna("").str.lower() == q.lower()).to_numpy()
        hits = np.concatenate([hits[exact], hits[~exact]])
    page = hits[offset : offset + limit]
    return {
        "total": len(hits),
        "offset": offset,
        "results": [neuron_record(store, i) for i in page],
    }


@router.get("/datasets/{dataset_id}/index/{idx}")
def neuron_at(dataset_id: str, idx: int):
    """Neuron by dense storage index (used for picking points in the 3D view)."""
    store = store_or_404(dataset_id)
    if not 0 <= idx < store.n_neurons:
        raise HTTPException(404, "index out of range")
    return neuron_record(store, idx)


@router.get("/datasets/{dataset_id}/neurons/{root_id}")
def neuron(dataset_id: str, root_id: str):
    store = store_or_404(dataset_id)
    ids = parse_root_ids(root_id)
    try:
        i = int(store.root_to_idx(ids)[0])
    except KeyError:
        raise HTTPException(404, f"neuron {root_id} not in {dataset_id}") from None
    rec = neuron_record(store, i)
    q = store.queries
    down = q.downstream(i)
    up = q.upstream(i)
    rec["connectivity"] = {
        "downstream_partners": len(down[0]),
        "upstream_partners": len(up[0]),
        "output_synapses": int(down[1].sum()),
        "input_synapses": int(up[1].sum()),
        "sign_of_outputs": int(down[2][0]) if len(down[2]) else None,
    }
    m = store.manifest
    rec["dataset"] = {"id": m.dataset_id, "version": m.dataset_version, "synthetic": m.synthetic}
    rec["source_url"] = (
        CODEX_URL.format(rid=root_id, v=m.dataset_version)
        if m.dataset_id.startswith("flywire")
        else None
    )
    rec["has_skeleton"] = _has_skeleton(dataset_id, int(ids[0]))
    return rec


def _has_skeleton(dataset_id: str, rid: int) -> bool:
    if dataset_id != geometry.SKELETON_DATASET:
        return False
    try:
        return geometry.SkeletonStore.get().has(rid)
    except geometry.SkeletonUnavailableError:
        return False


@router.get("/datasets/{dataset_id}/neurons/{root_id}/partners")
def partners(
    dataset_id: str,
    root_id: str,
    direction: Literal["downstream", "upstream"] = "downstream",
    min_syn: int = Query(1, ge=1, le=10000),
    limit: int = Query(200, ge=1, le=5000),
):
    store = store_or_404(dataset_id)
    try:
        i = int(store.root_to_idx(parse_root_ids(root_id))[0])
    except KeyError:
        raise HTTPException(404, f"neuron {root_id} not in {dataset_id}") from None
    q = store.queries
    idx, cnt, sgn = (
        q.downstream(i, min_syn) if direction == "downstream" else q.upstream(i, min_syn)
    )
    order = np.argsort(-cnt, kind="stable")[:limit]
    nb = store.neurons
    w_syn = LIFParams().w_syn_mV
    total = int(cnt.sum())
    rows = []
    for k in order:
        j = int(idx[k])
        rows.append(
            {
                "root_id": str(int(nb.at[j, "root_id"])),
                "idx": j,
                "cell_type": _s(nb.at[j, "cell_type"]),
                "super_class": _s(nb.at[j, "super_class"]),
                "side": _s(nb.at[j, "side"]),
                "nt_type": _s(nb.at[j, "nt_type"]),
                "primary_neuropil": _s(nb.at[j, "primary_neuropil"]),
                "syn_count": int(cnt[k]),
                "sign": int(sgn[k]),
                "fraction_of_total": float(cnt[k] / total) if total else 0.0,
                "model_weight_mV": float(sgn[k] * cnt[k] * w_syn),
            }
        )
    return {
        "root_id": root_id,
        "direction": direction,
        "min_syn": min_syn,
        "n_partners": len(idx),
        "total_synapses": total,
        "partners": rows,
        "measures": {
            "syn_count": "number of reconstructed synapses (EM)",
            "sign": "+1/-1 from predicted presynaptic transmitter (assumption)",
            "model_weight_mV": "sign x syn_count x w_syn used by the LIF model",
        },
    }


def _s(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)


@router.get("/datasets/{dataset_id}/pathways")
def pathways(
    dataset_id: str,
    source: str,
    target: str,
    min_syn: int = Query(5, ge=1),
    max_depth: int = Query(6, ge=1, le=10),
):
    store = store_or_404(dataset_id)
    src = store.root_to_idx(parse_root_ids(source), strict=False)
    tgt = store.root_to_idx(parse_root_ids(target), strict=False)
    src, tgt = src[src >= 0], tgt[tgt >= 0]
    if not len(src) or not len(tgt):
        raise HTTPException(404, "source or target not found")
    path = store.queries.shortest_path(src, tgt, min_syn, max_depth)
    if path is None:
        return {
            "found": False,
            "path": [],
            "edges": [],
            "message": f"no directed path with >= {min_syn} synapses per hop within "
            f"{max_depth} hops",
        }
    edges = []
    for a, b in zip(path[:-1], path[1:], strict=True):
        post, cnt, sgn = store.queries.downstream(a, 1)
        k = int(np.nonzero(post == b)[0][0])
        edges.append(
            {
                "pre": str(int(store.idx_to_root([a])[0])),
                "post": str(int(store.idx_to_root([b])[0])),
                "syn_count": int(cnt[k]),
                "sign": int(sgn[k]),
            }
        )
    return {"found": True, "path": [neuron_record(store, i) for i in path], "edges": edges}


@router.get("/datasets/{dataset_id}/subgraph")
def subgraph(
    dataset_id: str,
    seeds: str,
    depth: int = Query(1, ge=0, le=3),
    direction: Literal["downstream", "upstream", "both"] = "both",
    min_syn: int = Query(5, ge=1),
    max_nodes: int = Query(300, ge=1, le=3000),
    format: Literal["json", "csv"] = "json",
):
    store = store_or_404(dataset_id)
    seed_idx = store.root_to_idx(parse_root_ids(seeds), strict=False)
    seed_idx = seed_idx[seed_idx >= 0]
    if not len(seed_idx):
        raise HTTPException(404, "no seed neurons found")
    hops = store.queries.neighborhood(seed_idx, depth, direction, min_syn, max_nodes)
    nodes = np.array(sorted(hops))
    sub, gidx = store.graph.subgraph(nodes)
    pre = gidx[sub.pre_indices()]
    post = gidx[np.asarray(sub.indices)]
    keep = np.asarray(sub.syn_count) >= min_syn
    root = store.neurons["root_id"].to_numpy()
    edges = pd.DataFrame(
        {
            "pre_root_id": root[pre[keep]].astype(str),
            "post_root_id": root[post[keep]].astype(str),
            "syn_count": np.asarray(sub.syn_count)[keep],
            "sign": np.asarray(sub.sign)[keep],
        }
    )
    if format == "csv":
        buf = io.StringIO()
        edges.to_csv(buf, index=False)
        return Response(
            buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{dataset_id}_subgraph.csv"'},
        )
    nb = store.neurons
    return {
        "nodes": [{**neuron_record(store, int(i)), "hop": hops[int(i)]} for i in nodes],
        "edges": edges.to_dict(orient="records"),
        "truncated": len(hops) >= max_nodes,
        "params": {"depth": depth, "direction": direction, "min_syn": min_syn},
        "note": "Edges are reconstructed synaptic connections; spatial proximity in 3D does not "
        "imply connectivity.",
        "n_dataset_neurons": len(nb),
    }


# ----------------------------------------------------------------- geometry
@router.get("/datasets/{dataset_id}/points")
def points(dataset_id: str):
    store = store_or_404(dataset_id)
    arr = geometry.positions_um(store)
    return Response(
        arr.tobytes(),
        media_type="application/octet-stream",
        headers={"X-Count": str(len(arr)), "X-Units": "um", "Cache-Control": "max-age=3600"},
    )


@router.get("/datasets/{dataset_id}/attributes/{field}")
def attributes(dataset_id: str, field: str):
    store = store_or_404(dataset_id)
    try:
        return geometry.category_codes(store, field)
    except KeyError:
        raise HTTPException(404, f"unknown attribute {field}") from None


@router.get("/datasets/{dataset_id}/neuropils")
def neuropils(dataset_id: str):
    store = store_or_404(dataset_id)
    return {
        "centroids": geometry.neuropil_centroids(store),
        "note": "Neuropil label positions are medians of neuron positions assigned to each "
        "neuropil (not neuropil meshes).",
    }


@router.get("/datasets/{dataset_id}/skeletons/{root_id}")
def skeleton(dataset_id: str, root_id: str, lod: int = Query(1, ge=0, le=2)):
    store_or_404(dataset_id)
    rid = parse_root_ids(root_id)[0]
    if dataset_id != geometry.SKELETON_DATASET:
        raise HTTPException(
            404,
            detail={
                "error": "geometry_unavailable",
                "message": "No reconstructed geometry exists for this "
                "dataset (synthetic or ID-only).",
            },
        )
    try:
        return geometry.skeleton_payload(rid, lod)
    except geometry.SkeletonUnavailableError as exc:
        raise HTTPException(
            404, detail={"error": "skeletons_not_installed", "message": str(exc)}
        ) from None
    except KeyError:
        raise HTTPException(
            404, detail={"error": "geometry_unavailable", "message": f"no skeleton for {root_id}"}
        ) from None


# ------------------------------------------------------------------- groups
@router.get("/datasets/{dataset_id}/groups")
def groups(dataset_id: str):
    store = store_or_404(dataset_id)
    out = []
    for name, g in load_groups(dataset_id).items():
        try:
            idx = resolve(store, NeuronSelector(group=name))
            n = len(idx)
            ids = [str(int(r)) for r in store.idx_to_root(idx[:2000])]
        except (KeyError, ValueError):
            n, ids = 0, []
        out.append(
            {
                "name": name,
                "description": g.get("description", ""),
                "source": g.get("source", ""),
                "evidence": g.get("evidence"),
                "user_defined": g.get("user_defined", False),
                "n_neurons": n,
                "root_ids": ids,
            }
        )
    return out


class GroupIn(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    root_ids: list[int] = Field(min_length=1, max_length=20000)
    description: str = Field("", max_length=500)


@router.post("/datasets/{dataset_id}/groups")
def create_group(dataset_id: str, body: GroupIn):
    store = store_or_404(dataset_id)
    try:
        store.root_to_idx(body.root_ids)
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from None
    save_group(dataset_id, body.name, body.root_ids, body.description, "user (FlyMind UI)")
    return {"saved": body.name, "n_neurons": len(body.root_ids)}
