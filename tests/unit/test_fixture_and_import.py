import gzip
import json

import numpy as np
import pytest

from flymind.connectome.detect import detect_file, scan_directory
from flymind.connectome.fixtures import FIXTURE_ID
from flymind.connectome.store import ConnectomeStore
from flymind.connectome.validate import validate_dataset


def test_fixture_is_flagged_synthetic_and_validates(store):
    m = store.manifest
    assert m.synthetic and m.dataset_id == FIXTURE_ID
    assert all(t.startswith("syn_") for t in store.neurons["cell_type"])
    rep = validate_dataset(store.directory)
    assert rep.status == "passed", [c for c in rep.checks if c.status != "pass"]


def test_root_id_mapping_roundtrip(store):
    ids = store.neurons["root_id"].to_numpy()[[0, 5, 77]]
    assert store.idx_to_root(store.root_to_idx(ids)).tolist() == ids.tolist()
    with pytest.raises(KeyError):
        store.root_to_idx([123])
    assert store.root_to_idx([123], strict=False).tolist() == [-1]


def _write_codex(dirpath, ids, edges):
    """Tiny files with the exact FlyWire Codex v783 headers."""
    with gzip.open(dirpath / "neurons.csv.gz", "wt", newline="") as fh:
        fh.write(
            "root_id,group,nt_type,nt_type_score,da_avg,ser_avg,gaba_avg,glut_avg,ach_avg,oct_avg\r\n"
        )
        for i, r in enumerate(ids):
            nt = "GABA" if i == 1 else "ACH"
            fh.write(f"{r},AL.AL_L,{nt},0.9,0,0,0,0,0.9,0\r\n")
    with gzip.open(dirpath / "classification.csv.gz", "wt", newline="") as fh:
        fh.write("root_id,flow,super_class,class,sub_class,hemilineage,side,nerve\r\n")
        for r in ids:
            fh.write(f"{r},intrinsic,central,,,,left,\r\n")
    with gzip.open(dirpath / "connections.csv.gz", "wt", newline="") as fh:
        fh.write("pre_root_id,post_root_id,neuropil,syn_count,nt_type\r\n")
        for pre, post, npil, cnt in edges:
            fh.write(f"{pre},{post},{npil},{cnt},ACH\r\n")
    (dirpath / "coordinates.csv.gz").write_bytes(
        gzip.compress(
            (
                "root_id,position,supervoxel_id\r\n"
                + "".join(f"{r},[{100000 + i} 2000 300],1\r\n" for i, r in enumerate(ids))
            ).encode()
        )
    )


def test_codex_import_preserves_ids_and_aggregates(tmp_path):
    from flymind.connectome.importer import import_directory

    ids = [720575940629970489, 720575940621014292, 720575940624201033]
    edges = [(ids[0], ids[1], "AL_L", 6), (ids[0], ids[1], "LH_L", 4), (ids[1], ids[2], "AL_L", 9)]
    src = tmp_path / "codex"
    src.mkdir()
    _write_codex(src, ids, edges)
    roles = {d.role for d in scan_directory(src)}
    assert {
        "codex_neurons",
        "codex_classification",
        "codex_connections",
        "codex_coordinates",
    } <= roles
    out = import_directory(src, connectivity="codex", out_root=tmp_path / "processed")
    s = ConnectomeStore(out)
    assert s.neurons["root_id"].tolist() == sorted(ids)
    e = s.graph
    assert e.n_edges == 2 and e.n_synapses == 19  # 6+4 aggregated over neuropils
    i0, i1 = s.root_to_idx([ids[0], ids[1]])
    post, cnt, sgn = e.downstream(int(i0))
    assert post.tolist() == [i1] and cnt.tolist() == [10] and sgn.tolist() == [1]
    assert s.graph.downstream(int(i1))[2].tolist() == [-1]  # GABA presynaptic -> inhibitory
    rep = json.loads((out / "validation_report.json").read_text())
    assert rep["status"] in ("passed", "passed_with_warnings")
    assert s.neurons["pos_x"].iloc[0] == pytest.approx(100000 + ids.index(sorted(ids)[0]))
    assert s.manifest.files and all(len(f.sha256) == 64 for f in s.manifest.files)


def test_import_rejects_ids_from_another_release(tmp_path):
    from flymind.connectome.importer import import_directory

    ids = [720575940629970489, 720575940621014292]
    src = tmp_path / "mixed"
    src.mkdir()
    _write_codex(src, ids, [(ids[0], 720575940699999999, "AL_L", 5)])
    with pytest.raises(ValueError):
        import_directory(src, connectivity="codex", out_root=tmp_path / "p2")


def test_detection_is_by_content_not_name(tmp_path):
    p = tmp_path / "whatever.bin"
    p.write_text(
        "root_id,flow,super_class,class,sub_class,hemilineage,side,nerve\n1,a,b,c,d,e,f,g\n"
    )
    assert detect_file(p).role == "codex_classification"
    q = tmp_path / "neurons.csv"
    q.write_text("hello,world\n")
    assert detect_file(q) is None
    np.save(tmp_path / "ids.npy", np.array([1, 2], dtype=np.uint64))
    assert detect_file(tmp_path / "ids.npy").role == "zenodo_root_ids"
