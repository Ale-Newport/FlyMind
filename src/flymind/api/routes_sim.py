"""Brain simulation session endpoints and WebSocket streaming."""

from __future__ import annotations

import asyncio
import io
import json
from typing import Literal

import numpy as np
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field

from flymind.api.common import jsonable, parse_root_ids
from flymind.brain.recording import population_rate
from flymind.brain.session import InterventionSpec, SessionConfig, StimulusSpec
from flymind.common.paths import experiments_dir, safe_join, validate_identifier
from flymind.common.provenance import runtime_provenance, utc_now
from flymind.connectome.selectors import NeuronSelector, resolve

router = APIRouter(prefix="/api/sim")
ws_router = APIRouter()


def _state(request: Request):
    return request.app.state.service


def _session(request: Request, sid: str):
    try:
        return _state(request).sims.get(sid)
    except KeyError:
        raise HTTPException(404, f"no simulation session {sid}") from None


def _err(exc: Exception) -> HTTPException:
    return HTTPException(422 if isinstance(exc, ValueError | KeyError) else 409, str(exc))


@router.post("/sessions")
def create(request: Request, cfg: SessionConfig):
    try:
        s = _state(request).sims.create(cfg)
    except (ValueError, KeyError, RuntimeError) as exc:
        raise _err(exc) from None
    return s.summary()


@router.get("/sessions")
def list_sessions(request: Request):
    return [s.summary() for s in _state(request).sims.list()]


@router.get("/sessions/{sid}")
def get(request: Request, sid: str):
    return _session(request, sid).summary()


@router.delete("/sessions/{sid}")
def delete(request: Request, sid: str):
    _state(request).sims.delete(sid)
    return {"deleted": sid}


class Control(BaseModel):
    action: Literal["start", "pause", "resume", "stop", "reset", "step", "speed"]
    n_steps: int = Field(1, ge=1, le=100_000)
    seed: int | None = Field(None, ge=0, le=2**31 - 1)
    speed: float | None = Field(None, gt=0, le=1000)


@router.post("/sessions/{sid}/control")
def control(request: Request, sid: str, body: Control):
    s = _session(request, sid)
    try:
        if body.action == "start":
            s.start()
        elif body.action == "pause":
            s.pause()
        elif body.action == "resume":
            s.resume()
        elif body.action == "stop":
            s.stop()
        elif body.action == "reset":
            s.reset(body.seed)
        elif body.action == "step":
            frame = s.step(body.n_steps)
            return {
                **s.summary(),
                "frame": {k: frame[k] for k in ("t_ms", "spike_t_ms", "spike_idx")},
            }
        elif body.action == "speed":
            s.set_speed(body.speed)
    except (RuntimeError, ValueError) as exc:
        raise _err(exc) from None
    return s.summary()


class StimIn(StimulusSpec):
    relative: bool = Field(False, description="start/stop relative to the current sim time")


@router.post("/sessions/{sid}/stimuli")
def add_stimulus(request: Request, sid: str, body: StimIn):
    s = _session(request, sid)
    try:
        spec = StimulusSpec(**body.model_dump(exclude={"relative"}))
        return {"id": s.add_stimulus(spec, relative=body.relative), **s.summary()}
    except (ValueError, KeyError) as exc:
        raise _err(exc) from None


@router.delete("/sessions/{sid}/stimuli/{stim_id}")
def remove_stimulus(request: Request, sid: str, stim_id: str):
    s = _session(request, sid)
    if not s.remove_stimulus(stim_id):
        raise HTTPException(404, f"no stimulus {stim_id}")
    return s.summary()


@router.post("/sessions/{sid}/interventions")
def add_intervention(request: Request, sid: str, body: InterventionSpec):
    s = _session(request, sid)
    try:
        return {"id": s.add_intervention(body), **s.summary()}
    except (ValueError, KeyError) as exc:
        raise _err(exc) from None


@router.delete("/sessions/{sid}/interventions/{item_id}")
def remove_intervention(request: Request, sid: str, item_id: str):
    s = _session(request, sid)
    if not s.remove_intervention(item_id):
        raise HTTPException(404, f"no intervention {item_id}")
    return s.summary()


@router.post("/sessions/{sid}/interventions/clear")
def clear_interventions(request: Request, sid: str):
    s = _session(request, sid)
    s.clear_interventions()
    return s.summary()


class ProbesIn(BaseModel):
    root_ids: list[int] = Field(default_factory=list, max_length=64)


@router.post("/sessions/{sid}/probes")
def set_probes(request: Request, sid: str, body: ProbesIn):
    s = _session(request, sid)
    try:
        s.set_probes(body.root_ids)
    except (ValueError, KeyError) as exc:
        raise _err(exc) from None
    return s.summary()


@router.get("/sessions/{sid}/activity")
def activity(
    request: Request,
    sid: str,
    t0_ms: float = Query(0, ge=0),
    t1_ms: float | None = None,
    top: int = Query(50, ge=1, le=500),
):
    s = _session(request, sid)
    t1 = s.t_ms if t1_ms is None else min(t1_ms, s.t_ms)
    return s.activity(t0_ms, max(t1, t0_ms + s.config.params.dt_ms), top)


@router.get("/sessions/{sid}/raster")
def raster(
    request: Request,
    sid: str,
    t0_ms: float = Query(0, ge=0),
    t1_ms: float | None = None,
    neurons: str | None = None,
    max_spikes: int = Query(50_000, ge=1, le=500_000),
):
    s = _session(request, sid)
    t1 = s.t_ms if t1_ms is None else t1_ms
    steps, idx = s.spikes.window(t0_ms, t1)
    if neurons:
        sel = s.store.root_to_idx(parse_root_ids(neurons), strict=False)
        keep = np.isin(idx, sel[sel >= 0])
        steps, idx = steps[keep], idx[keep]
    truncated = len(steps) > max_spikes
    steps, idx = steps[-max_spikes:], idx[-max_spikes:]
    return {
        "t0_ms": t0_ms,
        "t1_ms": t1,
        "truncated": truncated,
        "t_ms": (steps * s.config.params.dt_ms).round(2).tolist(),
        "idx": idx.tolist(),
    }


@router.get("/sessions/{sid}/traces")
def traces(request: Request, sid: str, t0_ms: float = 0.0, max_points: int = Query(4000, le=20000)):
    s = _session(request, sid)
    t, v = s.probe_traces()
    keep = t >= t0_ms
    t, v = t[keep], v[keep]
    if len(t) > max_points:
        step = int(np.ceil(len(t) / max_points))
        t, v = t[::step], v[::step]
    return {
        "root_ids": [str(int(s.root_ids[i])) for i in s.probe_idx],
        "t_ms": t.tolist(),
        "v_mV": v.T.round(3).tolist(),
        "units": "mV",
        "note": "membrane potential of the simulated point neuron (model variable)",
    }


@router.get("/sessions/{sid}/population")
def population(
    request: Request,
    sid: str,
    groups: str = Query(..., max_length=2000),
    bin_ms: float = Query(10.0, gt=0, le=1000),
):
    s = _session(request, sid)
    steps, idx = s.spikes.arrays()
    out = {}
    for name in [g for g in groups.split(",") if g][:20]:
        if name.startswith("stim:"):
            spec = s.stimulus_specs.get(name[5:])
            if spec is None:
                continue
            members = resolve(s.store, spec.selector)
        else:
            try:
                members = resolve(s.store, NeuronSelector(group=name))
            except KeyError:
                continue
        members = members[s.network.local_of[members] >= 0]
        t, r = population_rate(steps, idx, members, 0.0, s.t_ms, bin_ms, s.config.params.dt_ms)
        out[name] = {"n_neurons": len(members), "t_ms": t.tolist(), "rate_hz": r.tolist()}
    return {"bin_ms": bin_ms, "groups": out}


@router.get("/sessions/{sid}/export")
def export(request: Request, sid: str, format: Literal["parquet", "csv", "json"] = "parquet"):
    s = _session(request, sid)
    df = s.spikes_frame()
    if format == "parquet":
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return Response(
            buf.getvalue(),
            media_type="application/vnd.apache.parquet",
            headers={"Content-Disposition": f'attachment; filename="spikes_{sid}.parquet"'},
        )
    if format == "csv":
        df = df.assign(root_id=df["root_id"].astype(str))
        return Response(
            df.to_csv(index=False),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="spikes_{sid}.csv"'},
        )
    payload = {
        "session": s.summary(),
        "actions": s.actions,
        "spikes": {"t_ms": df["t_ms"].tolist(), "root_id": df["root_id"].astype(str).tolist()},
    }
    return Response(
        json.dumps(jsonable(payload)),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="session_{sid}.json"'},
    )


@router.post("/sessions/{sid}/save")
def save(request: Request, sid: str):
    """Persist the session (config, action log, spikes, provenance) as an experiment record."""
    s = _session(request, sid)
    name = validate_identifier(f"session_{utc_now().replace(':', '').replace('-', '')}_{sid}")
    out = safe_join(experiments_dir(), name)
    out.mkdir(parents=True, exist_ok=True)
    s.spikes_frame().to_parquet(out / "spikes.parquet", index=False)
    t, v = s.probe_traces()
    if len(t):
        import pandas as pd

        pd.DataFrame(v, columns=[str(int(s.root_ids[i])) for i in s.probe_idx]).assign(
            t_ms=t
        ).to_parquet(out / "probes.parquet", index=False)
    record = {
        "experiment_id": name,
        "kind": "interactive_session",
        "name": s.config.label or name,
        "created_at": utc_now(),
        "session": s.summary(),
        "config": s.config.model_dump(),
        "actions": s.actions,
        "dataset": {
            "dataset_id": s.store.manifest.dataset_id,
            "version": s.store.manifest.dataset_version,
            "synthetic": s.store.manifest.synthetic,
            "files": [f.model_dump() for f in s.store.manifest.files],
        },
        "evidence": "demonstration" if s.store.manifest.synthetic else "simulation_output",
        "runtime": runtime_provenance(),
        "replay": "Re-create the session from config, then apply `actions` in order at their t_ms.",
    }
    (out / "record.json").write_text(json.dumps(jsonable(record), indent=2) + "\n")
    return {"experiment_id": name}


# ------------------------------------------------------------------ websocket
def _merge(frames: list[dict], max_spikes: int) -> dict:
    last = frames[-1]
    t, idx, pt, pv = [], [], [], None
    for f in frames:
        if f.get("type") != "frame":
            continue
        t += f["spike_t_ms"]
        idx += f["spike_idx"]
        pt += f["probe_t_ms"]
        pv = f["probe_v"] if pv is None else [a + b for a, b in zip(pv, f["probe_v"], strict=False)]
    truncated = len(t) > max_spikes
    return {
        "type": "frame",
        "t_ms": last.get("t_ms"),
        "status": last.get("status"),
        "sim_wall_ratio": last.get("sim_wall_ratio"),
        "wall_running_s": last.get("wall_running_s"),
        "n_spikes_total": last.get("n_spikes_total"),
        "spike_t_ms": t[-max_spikes:],
        "spike_idx": idx[-max_spikes:],
        "truncated": truncated,
        "probe_t_ms": pt,
        "probe_v": pv or [],
        "n_frames_merged": len(frames),
    }


@ws_router.websocket("/ws/sim/{sid}")
async def ws_sim(websocket: WebSocket, sid: str):
    service = websocket.app.state.service
    await websocket.accept()
    try:
        session = service.sims.get(sid)
    except KeyError:
        await websocket.send_json({"type": "error", "message": f"no session {sid}"})
        await websocket.close()
        return
    q = session.subscribe()
    opts = {"interval": 0.1, "max_spikes": 20_000}

    async def receiver():
        while True:
            msg = await websocket.receive_json()
            opts["interval"] = min(max(float(msg.get("interval_ms", 100)) / 1000, 0.03), 2.0)
            opts["max_spikes"] = int(min(max(msg.get("max_spikes", 20_000), 0), 200_000))

    rx = asyncio.create_task(receiver())
    last_status = session.status
    try:
        await websocket.send_json(jsonable({"type": "hello", "session": session.summary()}))
        while not rx.done():
            await asyncio.sleep(opts["interval"])
            frames = []
            while q:
                frames.append(q.popleft())
            if frames:
                await websocket.send_json(jsonable(_merge(frames, opts["max_spikes"])))
            if session.status != last_status:  # status messages only on change
                last_status = session.status
                await websocket.send_json(
                    {"type": "status", "status": session.status, "t_ms": session.t_ms}
                )
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        rx.cancel()
        session.unsubscribe(q)
