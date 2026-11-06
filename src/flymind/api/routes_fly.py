"""Virtual fly endpoints: sessions, meshes, recordings/replay, WebSocket streaming."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from flymind.api.common import jsonable
from flymind.brain.session import SimulationSession
from flymind.common.paths import experiments_dir, safe_join, validate_identifier
from flymind.embodiment.arena import ArenaConfig, arena_preset, odor_grid
from flymind.embodiment.bridge import BRIDGE_PRESETS
from flymind.embodiment.session import BaselineCommand, FlySessionConfig

router = APIRouter(prefix="/api/fly")
ws_router = APIRouter()
_mesh_cache: dict[str, object] = {}
_mesh_lock = threading.Lock()


def _state(request: Request):
    return request.app.state.service


def _fly(request: Request, sid: str):
    try:
        return _state(request).flies.get(sid)
    except KeyError:
        raise HTTPException(404, f"no fly session {sid}") from None


@router.get("/arenas")
def arenas():
    return [
        arena_preset(k).model_dump() for k in ("empty", "food", "obstacle", "light", "experimental")
    ]


@router.get("/bridges")
def bridges():
    return [b.model_dump() for b in BRIDGE_PRESETS.values()]


@router.post("/odor-field")
def odor_field(arena: ArenaConfig):
    return odor_grid(arena.odor_sources)


def _mesh_pack():
    with _mesh_lock:
        if "blob" not in _mesh_cache:
            from flymind.embodiment.body import FlyBody

            body = FlyBody(arena_preset("empty"))
            meta, blob = body.mesh_pack()
            _mesh_cache["meta"], _mesh_cache["blob"] = meta, blob
        return _mesh_cache["meta"], _mesh_cache["blob"]


@router.get("/meshes/meta")
def mesh_meta():
    return _mesh_pack()[0]


@router.get("/meshes/data")
def mesh_data():
    return Response(
        _mesh_pack()[1],
        media_type="application/octet-stream",
        headers={"Cache-Control": "max-age=86400"},
    )


@router.post("/sessions")
def create(request: Request, cfg: FlySessionConfig):
    service = _state(request)

    def brain_factory(brain_cfg) -> SimulationSession:
        return service.sims.create(brain_cfg)  # registered: explorer can read its activity

    try:
        s = service.flies.create(cfg, brain_factory=brain_factory)
    except (ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from None
    return {**s.summary(), "scene": s.body.scene_objects()}


@router.get("/sessions")
def list_sessions(request: Request):
    return [s.summary() for s in _state(request).flies.list()]


@router.get("/sessions/{sid}")
def get(request: Request, sid: str):
    s = _fly(request, sid)
    return {**s.summary(), "scene": s.body.scene_objects()}


@router.delete("/sessions/{sid}")
def delete(request: Request, sid: str):
    _state(request).flies.delete(sid)
    return {"deleted": sid}


class FlyControl(BaseModel):
    action: Literal["start", "pause", "resume", "stop", "reset"]


@router.post("/sessions/{sid}/control")
def control(request: Request, sid: str, body: FlyControl):
    s = _fly(request, sid)
    try:
        getattr(s, body.action)()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from None
    return s.summary()


@router.post("/sessions/{sid}/baseline")
def set_baseline(request: Request, sid: str, body: BaselineCommand):
    s = _fly(request, sid)
    if s.config.controller != "baseline":
        raise HTTPException(409, "session uses the neural controller")
    s.set_baseline(body)
    return s.summary()


@router.get("/sessions/{sid}/trajectory")
def trajectory(request: Request, sid: str, max_rows: int = 2000):
    s = _fly(request, sid)
    df = s.trajectory()
    if len(df) > max_rows:
        df = df.iloc[:: int(np.ceil(len(df) / max_rows))]
    return {
        "columns": list(df.columns),
        "rows": df.round(5).to_dict(orient="records"),
        "metrics": s.metrics(),
    }


@router.post("/sessions/{sid}/save")
def save(request: Request, sid: str):
    s = _fly(request, sid)
    out = s.save()
    return {"recording_id": out.name}


@router.get("/recordings")
def recordings():
    root = experiments_dir()
    out = []
    if root.exists():
        for d in sorted(root.glob("fly_*"), reverse=True):
            rec = d / "record.json"
            if rec.is_file():
                r = json.loads(rec.read_text())
                out.append(
                    {
                        "recording_id": d.name,
                        "created_at": r.get("created_at"),
                        "controller": r.get("controller"),
                        "label": r["config"].get("label"),
                        "arena": r["config"]["arena"]["name"],
                        "metrics": r.get("metrics"),
                        "evidence": r.get("evidence"),
                    }
                )
    return out


@router.get("/recordings/{rid}")
def recording(rid: str):
    validate_identifier(rid, "recording id")
    d = safe_join(experiments_dir(), rid)
    if not (d / "record.json").is_file():
        raise HTTPException(404, f"no recording {rid}")
    rec = json.loads((d / "record.json").read_text())
    traj = pd.read_parquet(d / "trajectory.parquet")
    frames = np.load(d / "frames.npz") if (d / "frames.npz").is_file() else None
    return {
        "record": rec,
        "trajectory": {"columns": list(traj.columns), "rows": traj.round(5).to_dict("records")},
        "frames": None
        if frames is None
        else {
            "t_s": frames["t_s"].tolist(),
            "shape": list(frames["poses"].shape),
            "poses_b64": base64.b64encode(frames["poses"].astype(np.float32).tobytes()).decode(),
        },
    }


@ws_router.websocket("/ws/fly/{sid}")
async def ws_fly(websocket: WebSocket, sid: str):
    service = websocket.app.state.service
    await websocket.accept()
    try:
        s = service.flies.get(sid)
    except KeyError:
        await websocket.send_json({"type": "error", "message": f"no fly session {sid}"})
        await websocket.close()
        return
    q = s.subscribe(maxlen=4)

    async def receiver():
        while True:
            await websocket.receive_text()

    rx = asyncio.create_task(receiver())
    try:
        await websocket.send_json(
            jsonable({"type": "hello", "session": s.summary(), "scene": s.body.scene_objects()})
        )
        period = 1.0 / s.config.stream_hz
        last_status = s.status
        while not rx.done():
            await asyncio.sleep(period)
            latest = None
            while q:
                latest = q.popleft()  # keep only the newest pose frame (backpressure)
            if latest is not None:
                await websocket.send_json(jsonable(latest))
            if s.status != last_status:  # status messages only on change
                last_status = s.status
                await websocket.send_json(
                    {"type": "status", "status": s.status, "t_s": s.body.t_s, "error": s.error}
                )
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        rx.cancel()
        s.unsubscribe(q)
