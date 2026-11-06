"""Export the SYNTHETIC fixture as static files for the GitHub Pages demo.

Writes apps/web/public/demo/: datasets.json, manifest.json, validation.json, points.bin,
attr_<field>.json, neuropils.json, groups.json, neurons.json, edges.json, sources.json,
evidence.json, params.json. Only synthetic data is exported (never FlyWire data).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "apps" / "web" / "public" / "demo"


def main() -> None:
    from flymind.api.common import jsonable, neuron_record
    from flymind.brain.params import PARAMETER_INFO, LIFParams
    from flymind.common.evidence import EVIDENCE_DESCRIPTIONS
    from flymind.connectome.fixtures import build_fixture
    from flymind.connectome.selectors import NeuronSelector, load_groups, resolve
    from flymind.connectome.store import ConnectomeStore
    from flymind.visualization import geometry

    tmp = Path(tempfile.mkdtemp())
    info = build_fixture(tmp)
    store = ConnectomeStore(tmp / info.dataset_id)
    assert store.manifest.synthetic, "only synthetic data may be exported"
    OUT.mkdir(parents=True, exist_ok=True)
    m = store.manifest

    def dump(name, obj):
        (OUT / name).write_text(json.dumps(jsonable(obj), separators=(",", ":")))

    dump(
        "datasets.json",
        [
            {
                "dataset_id": m.dataset_id,
                "name": m.dataset_name,
                "version": m.dataset_version,
                "specimen": m.specimen,
                "synthetic": True,
                "n_neurons": m.n_neurons,
                "n_edges": m.n_edges,
                "n_synapses": m.n_synapses,
                "license": m.license,
                "validation_status": m.validation_status,
                "imported_at": m.imported_at,
                "adapter": m.adapter,
                "has_skeletons": False,
            }
        ],
    )
    dump("manifest.json", m.model_dump())
    dump("validation.json", json.loads((store.directory / "validation_report.json").read_text()))
    (OUT / "points.bin").write_bytes(geometry.positions_um(store).tobytes())
    for field in (*geometry.CATEGORY_FIELDS, "cell_type"):
        dump(f"attr_{field}.json", geometry.category_codes(store, field))
    dump("neuropils.json", {"centroids": geometry.neuropil_centroids(store), "note": "synthetic"})
    groups = []
    for name, g in load_groups(m.dataset_id).items():
        idx = resolve(store, NeuronSelector(group=name))
        groups.append(
            {
                "name": name,
                "description": g.get("description", ""),
                "source": g.get("source", ""),
                "evidence": g.get("evidence"),
                "user_defined": False,
                "n_neurons": len(idx),
                "root_ids": [str(r) for r in store.idx_to_root(idx)],
            }
        )
    dump("groups.json", groups)
    dump("neurons.json", [neuron_record(store, i) for i in range(store.n_neurons)])
    g = store.graph
    dump(
        "edges.json",
        {
            "pre": g.pre_indices().tolist(),
            "post": g.indices.tolist(),
            "syn": g.syn_count.tolist(),
            "sign": g.sign.tolist(),
        },
    )
    dump(
        "sources.json",
        {
            "bundles": [],
            "adapters": [],
            "codex": {
                "url": "https://codex.flywire.ai/api/download",
                "note": "Run FlyMind locally to import FlyWire data.",
            },
            "license_note": "The public demo contains only synthetic data.",
        },
    )
    dump("evidence.json", {k.value: v for k, v in EVIDENCE_DESCRIPTIONS.items()})
    dump(
        "params.json",
        {
            "defaults": LIFParams().model_dump(),
            "info": {k: v.model_dump() for k, v in PARAMETER_INFO.items()},
        },
    )
    print(f"static demo written to {OUT}")


if __name__ == "__main__":
    main()
