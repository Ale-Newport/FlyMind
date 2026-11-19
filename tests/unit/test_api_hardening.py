"""Regression tests for the local-API hardening (host/origin guards, input bounds)."""

import threading

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture(scope="module")
def client(store):
    from flymind.api.app import create_app

    with TestClient(create_app(), base_url="http://127.0.0.1") as c:
        yield c


@pytest.fixture(scope="module")
def sid(client):
    s = client.post(
        "/api/sim/sessions",
        json={"dataset_id": "synthetic_demo_v1", "network": {"mode": "demo"}},
    ).json()
    client.post(f"/api/sim/sessions/{s['id']}/control", json={"action": "step", "n_steps": 50})
    return s["id"]


def test_foreign_host_header_is_rejected(client):
    """DNS rebinding: a page on evil.example resolved to 127.0.0.1 must not reach the API."""
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health", headers={"Host": "localhost:8000"}).status_code == 200
    assert client.get("/api/health", headers={"Host": "[::1]:8000"}).status_code == 200
    r = client.get("/api/health", headers={"Host": "evil.example"})
    assert r.status_code == 400 and r.json()["detail"] == "invalid Host header"


def test_websocket_origin_is_checked(client, sid):
    with client.websocket_connect(
        f"ws://127.0.0.1/ws/sim/{sid}", headers={"Origin": "http://127.0.0.1:5173"}
    ) as ws:
        assert ws.receive_json()["type"] == "hello"
    with client.websocket_connect(
        f"ws://127.0.0.1/ws/sim/{sid}", headers={"Origin": "http://127.0.0.1"}
    ) as ws:
        assert ws.receive_json()["type"] == "hello"  # same origin as the API
    with client.websocket_connect(
        f"ws://127.0.0.1/ws/sim/{sid}", headers={"Origin": "http://localhost:5180"}
    ) as ws:
        assert ws.receive_json()["type"] == "hello"  # a local dev server on another port
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"ws://127.0.0.1/ws/sim/{sid}", headers={"Origin": "http://evil.example"}
        ) as ws:
            ws.receive_json()


def test_oversized_body_is_rejected(client):
    from flymind.api.guards import DEFAULT_MAX_BODY_BYTES

    big = b'{"x":"' + b"a" * (DEFAULT_MAX_BODY_BYTES + 10) + b'"}'
    r = client.post("/api/sim/sessions", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_invalid_identifiers_give_404_not_500(client):
    assert client.get("/api/experiments/a..b").status_code == 404
    assert client.get("/api/fly/recordings/a..b").status_code == 404
    r = client.post("/api/experiments/compare", json={"a": "a..b", "b": "x"})
    assert r.status_code == 404


def test_identifier_with_trailing_newline_is_invalid():
    from flymind.common.paths import validate_identifier

    assert validate_identifier("abc") == "abc"
    with pytest.raises(ValueError):
        validate_identifier("abc\n")


def test_downsampling_and_binning_bounds(client, sid):
    for mp in (-1, 0, 1):
        assert client.get(f"/api/sim/sessions/{sid}/traces?max_points={mp}").status_code == 422
    r = client.get(f"/api/sim/sessions/{sid}/population?groups=chain_a&bin_ms=0.000001")
    assert r.status_code == 422
    assert client.get(f"/api/sim/sessions/{sid}/population?groups=chain_a").status_code == 200


def test_population_rate_refuses_huge_bin_counts():
    from flymind.brain.recording import population_rate

    z = np.zeros(0, dtype=np.int64)
    with pytest.raises(ValueError):
        population_rate(z, z, np.array([0]), 0.0, 1e6, 1e-6, 0.1)


def test_condition_overrides_are_validated():
    from pydantic import ValidationError

    from flymind.experiments.spec import ExperimentSpec

    base = {"name": "x", "dataset_id": "synthetic_demo_v1"}
    ExperimentSpec(**base, conditions=[{"name": "a", "params": {"dt_ms": 0.1}}])
    for bad in ({"dt_ms": 1e-9 - 1}, {"dt_ms": 0}, {"tau_m_ms": "x"}):
        with pytest.raises(ValidationError):
            ExperimentSpec(**base, conditions=[{"name": "a", "params": bad}])


def test_job_queue_is_bounded_and_pruned():
    import time

    from flymind.api.state import JobQueueFull, JobRunner

    def wait_idle(runner):
        for _ in range(200):
            if all(j.status not in ("queued", "running") for j in runner.snapshot()):
                return
            time.sleep(0.01)

    gate = threading.Event()
    runner = JobRunner(workers=1, max_active=2, keep_finished=1)
    try:
        runner.submit("t", "a", lambda job: gate.wait(5))
        runner.submit("t", "b", lambda job: gate.wait(5))
        with pytest.raises(JobQueueFull):
            runner.submit("t", "c", lambda job: None)
        gate.set()
        wait_idle(runner)
        assert all(j.status == "done" and j.finished_at for j in runner.snapshot())
        for label in ("d", "e", "f"):
            runner.submit("t", label, lambda job: None)
            wait_idle(runner)
        assert len(runner.snapshot()) <= 2  # finished jobs beyond keep_finished are evicted
    finally:
        gate.set()
        runner.shutdown()


def test_cancelled_queued_job_records_finish_time():
    from flymind.api.state import JobRunner

    gate = threading.Event()
    runner = JobRunner(workers=1)
    try:
        runner.submit("t", "blocker", lambda job: gate.wait(5))
        queued = runner.submit("t", "queued", lambda job: None)
        queued.cancel.set()
        gate.set()
        runner.pool.shutdown(wait=True)
        assert queued.status == "cancelled" and queued.finished_at is not None
    finally:
        gate.set()


def test_spike_record_length_is_a_running_count():
    from flymind.brain.recording import SpikeRecord

    buf = SpikeRecord(dt_ms=0.1)
    buf.append(np.array([1, 2]), np.array([0, 1]))
    buf.append(np.array([3]), np.array([2]))
    assert len(buf) == 3 == len(buf.arrays()[0])
    buf.clear()
    assert len(buf) == 0


def test_brain_sessions_of_flies_are_never_evicted(store):
    from flymind.brain.session import SessionConfig, SessionManager

    cfg = SessionConfig(dataset_id="synthetic_demo_v1", network={"mode": "demo"})
    mgr = SessionManager(max_sessions=2)
    try:
        pinned = mgr.create(cfg, pinned=True)
        a = mgr.create(cfg)
        b = mgr.create(cfg)  # evicts `a`, never the pinned brain
        ids = {s.id for s in mgr.list()}
        assert ids == {pinned.id, b.id} and a.id not in ids
        mgr.delete(b.id)
        mgr.create(cfg, pinned=True)
        with pytest.raises(RuntimeError):  # every slot is held by a fly's brain
            mgr.create(cfg)
    finally:
        mgr.shutdown()
