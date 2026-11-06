import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(store):
    from flymind.api.app import create_app

    with TestClient(create_app()) as c:
        yield c


def test_datasets_and_neuron_queries_keep_ids_exact(client, store):
    ds = client.get("/api/datasets").json()
    assert [d["dataset_id"] for d in ds] == ["synthetic_demo_v1"] and ds[0]["synthetic"]
    r = client.get("/api/datasets/synthetic_demo_v1/neurons", params={"q": "syn_DN_turn_L"}).json()
    assert r["total"] == 5
    rid = r["results"][0]["root_id"]
    assert isinstance(rid, str) and int(rid) > 2**53  # never a lossy JSON number
    n = client.get(f"/api/datasets/synthetic_demo_v1/neurons/{rid}").json()
    assert n["root_id"] == rid and n["connectivity"]["upstream_partners"] > 0
    p = client.get(
        f"/api/datasets/synthetic_demo_v1/neurons/{rid}/partners", params={"direction": "upstream"}
    ).json()
    assert all(isinstance(x["root_id"], str) for x in p["partners"])
    assert sum(x["syn_count"] for x in p["partners"]) == p["total_synapses"]
    pts = client.get("/api/datasets/synthetic_demo_v1/points")
    assert len(pts.content) == 12 * store.n_neurons
    assert client.get("/api/datasets/synthetic_demo_v1/skeletons/" + rid).status_code == 404


def test_path_traversal_and_unknown_dataset_rejected(client):
    for url in (
        "/api/datasets/..%2F..%2Fetc",
        "/..%2F..%2Fpyproject.toml",
        "/%2e%2e/pyproject.toml",
    ):
        r = client.get(url)
        assert "[project]" not in r.text  # never serves files outside the web build
    assert client.get("/api/datasets/a..b").status_code == 404
    assert client.get("/api/datasets/not_installed/neurons").status_code == 404
    assert client.get("/api/experiments/..%2Fsecret").status_code in (404, 422)
    assert client.get("/api/experiments/x/files/../../pyproject.toml").status_code == 404


def test_simulation_session_lifecycle_and_stream(client):
    s = client.post(
        "/api/sim/sessions",
        json={
            "dataset_id": "synthetic_demo_v1",
            "network": {"mode": "demo"},
            "max_duration_ms": 300,
            "stimuli": [{"kind": "poisson", "selector": {"group": "chain_a"}, "rate_hz": 100}],
        },
    ).json()
    sid = s["id"]
    r = client.post(
        f"/api/sim/sessions/{sid}/control", json={"action": "step", "n_steps": 100}
    ).json()
    assert r["t_ms"] == pytest.approx(10.0) and r["status"] == "paused"
    sil = client.post(
        f"/api/sim/sessions/{sid}/interventions",
        json={"kind": "silence", "selector": {"group": "chain_b"}},
    ).json()
    assert len(sil["interventions"]) == 1
    client.post(f"/api/sim/sessions/{sid}/interventions/clear")
    with client.websocket_connect(f"/ws/sim/{sid}") as ws:
        assert ws.receive_json()["type"] == "hello"
        client.post(f"/api/sim/sessions/{sid}/control", json={"action": "resume"})
        msg = ws.receive_json()
        assert msg["type"] in ("frame", "status")
    for _ in range(100):
        if client.get(f"/api/sim/sessions/{sid}").json()["status"] == "finished":
            break
        time.sleep(0.05)
    assert client.get(f"/api/sim/sessions/{sid}").json()["status"] == "finished"
    act = client.get(f"/api/sim/sessions/{sid}/activity", params={"t0_ms": 0}).json()
    assert act["n_active"] >= 1
    assert (
        client.get(f"/api/sim/sessions/{sid}/export", params={"format": "csv"}).status_code == 200
    )
    saved = client.post(f"/api/sim/sessions/{sid}/save").json()
    assert any(
        e["experiment_id"] == saved["experiment_id"] for e in client.get("/api/experiments").json()
    )


def test_invalid_inputs_are_rejected(client):
    bad = client.post(
        "/api/sim/sessions", json={"dataset_id": "synthetic_demo_v1", "max_duration_ms": -5}
    )
    assert bad.status_code == 422
    bad = client.post(
        "/api/sim/sessions",
        json={"dataset_id": "synthetic_demo_v1", "network": {"mode": "circuit"}},
    )
    assert bad.status_code == 422


def test_experiment_job_runs_to_completion(client):
    templates = client.get("/api/experiments/templates").json()
    tpl = next(t for t in templates if t["key"] == "repeated_stimuli")
    spec = tpl["spec"]
    spec["n_trials"] = 2
    job = client.post("/api/experiments/run", json={"spec": spec}).json()
    for _ in range(200):
        j = client.get(f"/api/jobs/{job['job_id']}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert j["status"] == "done", j
    e = client.get(f"/api/experiments/{j['result']['experiment_id']}").json()
    assert e["readouts"] and e["record"]["evidence"] == "demonstration"
