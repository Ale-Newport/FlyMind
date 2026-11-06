"""Closed-loop virtual-fly sessions: brain <-> bridge <-> FlyGym body, recorded and streamed.

Per bridge interval (default 1 ms = 10 physics steps = 10 neural steps; both
time steps are 0.1 ms):

1. read sensors from the MuJoCo state (odour at the antennae, eye luminance,
   obstacle contacts, food contact);
2. encode them as Poisson input to the mapped sensory neurons;
3. advance the brain by the interval;
4. decode smoothed descending-neuron rates into a descending command;
5. step the body (controller + physics) for the interval with that command.

The command therefore lags the neural activity that produced it by one interval.
The baseline controller replaces steps 2-4 with a user-specified command; the autonomous
controller replaces them with a scripted fly-like behaviour policy (a demonstration).

The command is an *intent* (forward drive, turn, walk or fly). Walking is executed by the
FlyGym physics, flight by the reduced-order flight model; ``LocomotionController`` runs the
transitions between them (see ``behavior.py`` and docs/scientific/flight.md).
"""

from __future__ import annotations

import collections
import json
import math
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from flymind.brain.session import SessionConfig, SimulationSession
from flymind.common.concurrency import YieldingLock
from flymind.common.logging import get_logger
from flymind.common.paths import experiments_dir, safe_join, validate_identifier
from flymind.common.provenance import runtime_provenance, utc_now
from flymind.connectome.selectors import NeuronSelector, resolve
from flymind.embodiment.arena import ArenaConfig, arena_preset
from flymind.embodiment.behavior import (
    AutonomousPolicy,
    Intent,
    LocomotionController,
    Observation,
    command_to_ds,
)
from flymind.embodiment.body import FlyBody
from flymind.embodiment.bridge import BRIDGE_PRESETS, BridgeConfig, MotorDecoder, SensoryEncoder

log = get_logger("embodiment.session")


LocomotionMode = Literal["walk", "fly"]


class CommandStep(BaseModel):
    t_s: float = Field(ge=0)
    forward: float = Field(ge=-1.2, le=1.2)
    turn: float = Field(ge=-1.0, le=1.0)
    locomotion: LocomotionMode | None = Field(None, description="switch walk/fly at this step")
    altitude_mm: float | None = Field(None, ge=2, le=40)


class BaselineCommand(BaseModel):
    """Scripted descending command (external controller only; no neural model)."""

    forward: float = Field(1.0, ge=-1.2, le=1.2)
    turn: float = Field(0.0, ge=-1.0, le=1.0, description=">0 steers left")
    turn_gain: float = Field(0.8, ge=0, le=2)
    schedule: list[CommandStep] = Field(default_factory=list, max_length=100)

    def state_at(self, t_s: float) -> tuple[float, float, LocomotionMode | None, float | None]:
        fwd, turn, loco, alt = self.forward, self.turn, None, None
        for st in self.schedule:
            if t_s >= st.t_s:
                fwd, turn = st.forward, st.turn
                loco = st.locomotion if st.locomotion is not None else loco
                alt = st.altitude_mm if st.altitude_mm is not None else alt
        return fwd, turn, loco, alt

    def at(self, t_s: float) -> np.ndarray:
        fwd, turn, _, _ = self.state_at(t_s)
        return command_to_ds(fwd, turn, self.turn_gain)


class FlySessionConfig(BaseModel):
    arena: ArenaConfig = Field(default_factory=lambda: arena_preset("empty"))
    controller: Literal["baseline", "neural", "autonomous"] = "baseline"
    locomotion: LocomotionMode = Field("walk", description="initial walk/fly mode (not autonomous)")
    altitude_mm: float = Field(8.0, ge=2, le=40, description="target flight height of the thorax")
    baseline: BaselineCommand = BaselineCommand()
    brain: SessionConfig | None = None
    bridge: str = "synthetic_demo"
    bridge_config: BridgeConfig | None = Field(None, description="overrides the preset")
    duration_s: float = Field(5.0, gt=0, le=120)
    vision: bool | None = Field(None, description="None: enabled when the arena has lights")
    stream_hz: float = Field(30.0, gt=0, le=60)
    record_hz: float = Field(100.0, gt=0, le=1000)
    speed: float | None = Field(None, gt=0, le=10, description="target sim/wall ratio")
    seed: int = Field(0, ge=0, le=2**31 - 1)
    label: str = ""


FlyStatus = Literal["ready", "running", "paused", "stopped", "finished", "error"]


class FlySession:
    def __init__(self, config: FlySessionConfig, brain_factory=None):
        self.id = uuid.uuid4().hex[:12]
        self.config = config
        self.created_at = utc_now()
        vision = config.vision if config.vision is not None else bool(config.arena.lights)
        self.body = FlyBody(config.arena, vision=vision, seed=config.seed)
        self.status: FlyStatus = "ready"
        self.error: str | None = None
        self._lock = YieldingLock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._subscribers: list[collections.deque] = []
        self.actions: list[dict] = []
        self.brain: SimulationSession | None = None
        self.bridge: BridgeConfig | None = None
        if config.controller == "neural":
            if config.brain is None:
                raise ValueError("neural controller needs a brain configuration")
            self.bridge = config.bridge_config or BRIDGE_PRESETS[config.bridge]
            if config.brain.dataset_id not in self.bridge.dataset_ids:
                raise ValueError(
                    f"bridge {self.bridge.name} is defined for "
                    f"{self.bridge.dataset_ids}, not {config.brain.dataset_id}"
                )
            brain_cfg = config.brain.model_copy(deep=True)
            brain_cfg.max_duration_ms = config.duration_s * 1000.0 + 1000.0
            brain_cfg.seed = config.seed
            self.brain = brain_factory(brain_cfg) if brain_factory else SimulationSession(brain_cfg)
            p = self.brain.config.params
            if not math.isclose(p.dt_ms / 1000.0, self.body.dt_s, rel_tol=1e-9):
                raise ValueError("neural dt must equal the physics time step (0.1 ms)")
            groups = self._resolve_groups()
            weight = p.poisson_weight_factor * p.w_syn_mV
            self.encoder = SensoryEncoder(self.bridge, groups, weight, p.dt_ms, config.seed)
            self.decoder = MotorDecoder(self.bridge, groups)
        self.loco = LocomotionController(self.body)
        self.mode: LocomotionMode = config.locomotion
        self.altitude_mm = config.altitude_mm
        self.policy: AutonomousPolicy | None = (
            AutonomousPolicy(config.arena, config.seed)
            if config.controller == "autonomous"
            else None
        )
        self.intent = Intent(locomotion=self.mode, altitude_mm=self.altitude_mm)
        self.n_takeoffs = 0
        self.n_touchdowns = 0
        interval_ms = self.bridge.interval_ms if self.bridge else 1.0
        self.k_steps = max(1, int(round(interval_ms / 1000.0 / self.body.dt_s)))
        self._init_recording()

    def _resolve_groups(self) -> dict[str, np.ndarray]:
        assert self.brain is not None and self.bridge is not None
        names = {c.group for c in self.bridge.sensory} | {m.group for m in self.bridge.motor}
        out, missing = {}, []
        for g in sorted(names):
            idx = resolve(self.brain.store, NeuronSelector(group=g))
            local = self.brain.network.local_of[idx]
            local = local[local >= 0]
            if len(local) == 0:
                missing.append(g)
            out[g] = local.astype(np.int64)
        self.missing_groups = missing
        return out

    # --------------------------------------------------------------- recording
    def _init_recording(self) -> None:
        self.rec_rows: list[dict] = []
        self.rec_joints: list[np.ndarray] = []
        self.rec_frames: list[np.ndarray] = []
        self.rec_frame_t: list[float] = []
        self._next_rec = 0.0
        self._next_frame = 0.0
        self.last_state: dict = {}
        self.wall_s = 0.0

    def _record(self, ds: np.ndarray, drive: dict, sensors: dict) -> None:
        b = self.body
        t = b.t_s
        pos = b.position()
        heading = b.heading_rad()
        speed = (
            float(np.linalg.norm(pos[:2] - b._prev_xy) / max(t - self._last_rec_t, 1e-9))
            if (hasattr(self, "_last_rec_t") and t > self._last_rec_t)
            else 0.0
        )
        row = {
            "t_s": t,
            "x_mm": pos[0],
            "y_mm": pos[1],
            "z_mm": pos[2],
            "heading_rad": heading,
            "speed_mm_s": speed,
            "ds_left": float(ds[0]),
            "ds_right": float(ds[1]),
            **{f"drive_{k}": float(v) for k, v in drive.items()},
            **{f"sensor_{k}": float(v) for k, v in sensors.items()},
            "locomotion": self.loco.state,
            "behavior": self.intent.label,
            "airborne": 1.0 if self.loco.airborne else 0.0,
        }
        if self.loco.airborne:
            fs = b.flight.state
            _, pitch, roll = b.flight.euler_deg()
            row.update(
                {
                    "pitch_deg": pitch,
                    "roll_deg": roll,
                    "speed_3d_mm_s": float(np.linalg.norm(fs.v)) * 1e3,
                    "vz_mm_s": float(fs.v[2]) * 1e3,
                    "wing_amp_l_deg": math.degrees(fs.wing[0]),
                    "wing_amp_r_deg": math.degrees(fs.wing[1]),
                }
            )
        if self.brain is not None:
            row.update({f"rate_{k}": v for k, v in self.decoder.rate.items()})
            row.update({f"input_{k}": v for k, v in self.encoder.last_rates.items()})
            row["brain_t_ms"] = self.brain.t_ms
            row["brain_spikes_total"] = len(self.brain.spikes)
        self.rec_rows.append(row)
        self.rec_joints.append(b.joint_angles())
        b._prev_xy = pos[:2].copy()
        self._last_rec_t = t
        self.last_state = row

    # ------------------------------------------------------------------ control
    def _log(self, action: str, **payload) -> None:
        self.actions.append({"t_s": self.body.t_s, "wall": utc_now(), "action": action, **payload})

    def start(self) -> None:
        with self._lock:
            if self.status == "running":
                return
            if self.status in ("finished", "stopped", "error"):
                raise RuntimeError(f"cannot start a {self.status} session; reset first")
            self.status = "running"
            self._log("start")
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._loop, daemon=True, name=f"fly-{self.id}"
                )
                self._thread.start()
            self._wake.set()

    def pause(self) -> None:
        with self._lock:
            if self.status == "running":
                self.status = "paused"
                self._log("pause")

    def resume(self) -> None:
        with self._lock:
            if self.status == "paused":
                self.status = "running"
                self._log("resume")
                self._wake.set()

    def stop(self) -> None:
        with self._lock:
            if self.status in ("running", "paused", "ready"):
                self.status = "stopped"
                self._log("stop")
            self._wake.set()

    def reset(self) -> None:
        self.stop()
        if self._thread is not None:
            self._thread.join(timeout=30)
        with self._lock:
            self.body.reset()
            self.loco.reset()
            if self.policy is not None:
                self.policy.reset()
            self.mode = self.config.locomotion
            self.altitude_mm = self.config.altitude_mm
            self.intent = Intent(locomotion=self.mode, altitude_mm=self.altitude_mm)
            self.n_takeoffs = self.n_touchdowns = 0
            if self.brain is not None:
                self.brain.reset(self.config.seed)
                self.encoder.rng = np.random.default_rng(
                    np.random.SeedSequence([self.config.seed, 0xB1D6E])
                )
                self.decoder.rate = {k: 0.0 for k in self.decoder.rate}
            self._init_recording()
            if hasattr(self, "_last_rec_t"):
                del self._last_rec_t
            self._thread = None
            self.status = "ready"
            self.error = None
            self._log("reset")

    def set_baseline(self, cmd: BaselineCommand) -> None:
        with self._lock:
            self.config.baseline = cmd
            self._log("set_baseline", command=cmd.model_dump())

    def set_locomotion(self, mode: LocomotionMode, altitude_mm: float | None = None) -> None:
        """Ask the fly to walk or fly (baseline and neural controllers; the autonomous policy
        decides by itself)."""
        with self._lock:
            self.mode = mode
            if altitude_mm is not None:
                self.altitude_mm = altitude_mm
            self._log("set_locomotion", mode=mode, altitude_mm=self.altitude_mm)

    def _silenced_local(self) -> np.ndarray:
        from flymind.brain.stimulus import Silencing

        items = [i for i in self.brain.engine.interventions if isinstance(i, Silencing)]
        if not items:
            return np.zeros(0, dtype=np.int64)
        lo = self.brain.network.local_of
        idx = lo[np.concatenate([np.asarray(i.targets, dtype=np.int64) for i in items])]
        return idx[idx >= 0]

    # ---------------------------------------------------------------- the loop
    def _intent(
        self, sensors: dict, ds_drive: tuple[np.ndarray, dict] | None
    ) -> tuple[Intent, np.ndarray, dict]:
        """The fly's intent this interval, its walking command and the drive summary."""
        b = self.body
        t = b.t_s
        if ds_drive is not None:  # neural
            ds, drive = ds_drive
            intent = Intent(
                float(drive["amplitude"]),
                float(drive["turn"]),
                self.mode,
                self.altitude_mm,
                label="neural drive",
            )
            return intent, ds, drive
        if self.policy is not None:  # autonomous demonstration policy
            pos = b.position()
            intent = self.policy.step(
                Observation(
                    t_s=t,
                    x_mm=float(pos[0]),
                    y_mm=float(pos[1]),
                    z_mm=float(pos[2]),
                    heading_rad=b.heading_rad(),
                    sensors=sensors,
                    airborne=self.loco.airborne,
                )
            )
            ds = command_to_ds(intent.forward, intent.turn)
            return intent, ds, {"forward": intent.forward, "turn": intent.turn}
        fwd, turn, loco, alt = self.config.baseline.state_at(t)
        if loco is not None and loco != self.mode:
            self.mode = loco
        if alt is not None:
            self.altitude_mm = alt
        ds = command_to_ds(fwd, turn, self.config.baseline.turn_gain)
        drive = {"forward": float(np.mean(ds)), "turn": float((ds[1] - ds[0]) / 2)}
        return Intent(fwd, turn, self.mode, self.altitude_mm, label="manual"), ds, drive

    def advance(self) -> None:
        """One bridge interval of the closed loop."""
        b = self.body
        sensors = b.sensors()
        ds_drive = None
        if self.brain is not None:
            t0 = self.brain.engine.t_step
            events = self.encoder.events(sensors, t0, self.k_steps)
            res = self.brain.advance_external(self.k_steps, events)
            self.decoder.update(
                res.spike_local,
                self.k_steps * self.brain.config.params.dt_ms,
                self._silenced_local(),
            )
            ds_drive = self.decoder.descending()
        intent, ds, drive = self._intent(sensors, ds_drive)
        self.intent = intent
        for ev in self.loco.advance(intent, ds, self.k_steps, b.dt_s):
            self._log(ev, behavior=intent.label)
            self.n_takeoffs += ev == "takeoff"
            self.n_touchdowns += ev == "touchdown"
        if b.t_s + 1e-12 >= self._next_rec:
            self._record(ds, drive, sensors)
            self._next_rec += 1.0 / self.config.record_hz
        if b.t_s + 1e-12 >= self._next_frame:
            self._emit_frame(ds, drive, sensors)
            self._next_frame += 1.0 / self.config.stream_hz
        if b.t_s >= self.config.duration_s - 1e-9:
            self.status = "finished"
            self._log("finished")

    @property
    def wing_display_hz(self) -> float:
        """Wingbeat frequency used when drawing: ~6 frames per cycle at the stream rate."""
        return self.config.stream_hz / 6.0

    def _emit_frame(self, ds, drive, sensors) -> None:
        poses = self.body.geom_poses(wing_phase=2 * math.pi * self.wing_display_hz * self.body.t_s)
        self.rec_frames.append(poses)
        self.rec_frame_t.append(self.body.t_s)
        frame = {
            "type": "frame",
            "t_s": self.body.t_s,
            "poses": np.round(poses, 5).ravel().tolist(),
            "pos": self.body.position().tolist(),
            "heading_rad": self.body.heading_rad(),
            "ds": [float(ds[0]), float(ds[1])],
            "drive": drive,
            "sensors": {k: float(v) for k, v in sensors.items()},
            "status": self.status,
            "wall_s": self.wall_s,
            "locomotion": self.loco.state,
            "behavior": self.intent.label,
        }
        if self.loco.airborne:
            frame["flight"] = self._flight_info()
        if self.brain is not None:
            frame["readout_hz"] = dict(self.decoder.rate)
            frame["input_hz"] = dict(self.encoder.last_rates)
            frame["brain"] = {"t_ms": self.brain.t_ms, "n_spikes": len(self.brain.spikes)}
        for q in list(self._subscribers):
            q.append(frame)

    def _flight_info(self) -> dict:
        fl = self.body.flight
        fs = fl.state
        _, pitch, roll = fl.euler_deg()
        return {
            "altitude_mm": (fl.altitude() - self.body.morphology.stand_height_m) * 1e3,
            "speed_mm_s": float(np.linalg.norm(fs.v[:2])) * 1e3,
            "vz_mm_s": float(fs.v[2]) * 1e3,
            "pitch_deg": pitch,
            "roll_deg": roll,
            "yaw_rate_deg_s": math.degrees(float(fs.omega[2])),
            "wing_amp_deg": [math.degrees(float(fs.wing[0])), math.degrees(float(fs.wing[1]))],
            "wing_centre_deg": [math.degrees(float(fs.wing[2])), math.degrees(float(fs.wing[3]))],
            "wing_pitch_deg": [math.degrees(float(fs.wing[4])), math.degrees(float(fs.wing[5]))],
            "wingbeat_hz": fl.freq_hz,
            "wing_display_hz": self.wing_display_hz,
            "thrust_over_weight": float(fl.diag.get("thrust_over_weight", 0.0)),
            "engaged": bool(fs.engaged),
        }

    def _loop(self) -> None:
        try:
            while True:
                with self._lock:
                    if self.status in ("stopped", "finished", "error"):
                        break
                    running = self.status == "running"
                if not running:
                    self._wake.wait(0.1)
                    self._wake.clear()
                    continue
                with self._lock:
                    t0 = time.perf_counter()
                    self.advance()
                    dt_wall = time.perf_counter() - t0
                    self.wall_s += dt_wall
                    speed = self.config.speed
                self._lock.yield_to_waiters()
                if speed:
                    target = self.k_steps * self.body.dt_s / speed
                    if target > dt_wall:
                        time.sleep(target - dt_wall)
        except Exception as exc:  # surfaced through status
            log.exception("fly session failed", extra={"session": self.id})
            with self._lock:
                self.status = "error"
                self.error = f"{type(exc).__name__}: {exc}"
        finally:
            for q in list(self._subscribers):
                q.append({"type": "status", "status": self.status, "t_s": self.body.t_s})

    def run_blocking(self) -> None:
        """Run to completion on the calling thread (batch experiments, tests)."""
        self.status = "running"
        self._log("run_blocking")
        t0 = time.perf_counter()
        while self.status == "running":
            self.advance()
        self.wall_s += time.perf_counter() - t0

    def subscribe(self, maxlen: int = 64) -> collections.deque:
        q: collections.deque = collections.deque(maxlen=maxlen)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    # ------------------------------------------------------------------ results
    def trajectory(self) -> pd.DataFrame:
        return pd.DataFrame(self.rec_rows)

    def metrics(self) -> dict:
        df = self.trajectory()
        if df.empty:
            return {}
        xy = df[["x_mm", "y_mm"]].to_numpy()
        steps = np.linalg.norm(np.diff(xy, axis=0), axis=1)
        heading = np.unwrap(df["heading_rad"].to_numpy())
        contact = (df.get("sensor_contact_left", 0) + df.get("sensor_contact_right", 0)) > 0
        contact = np.asarray(contact, dtype=bool)
        onsets = int(np.sum(contact[1:] & ~contact[:-1]) + (contact[0] if len(contact) else 0))
        dur = float(df["t_s"].iloc[-1] - df["t_s"].iloc[0]) if len(df) > 1 else 0.0
        m = {
            "duration_s": float(df["t_s"].iloc[-1]),
            "distance_travelled_mm": float(steps.sum()),
            "net_displacement_mm": float(np.linalg.norm(xy[-1] - xy[0])),
            "mean_speed_mm_s": float(steps.sum() / dur) if dur > 0 else 0.0,
            "heading_change_deg": float(np.degrees(heading[-1] - heading[0])),
            "total_abs_turning_deg": float(np.degrees(np.abs(np.diff(heading)).sum())),
            "collision_onsets": onsets,
            "time_in_contact_s": float(contact.mean() * dur) if len(contact) else 0.0,
            "time_on_food_s": float(df.get("sensor_on_food", pd.Series([0])).mean() * dur),
            "final_x_mm": float(xy[-1, 0]),
            "final_y_mm": float(xy[-1, 1]),
            "mean_abs_descending": float(np.abs(df[["ds_left", "ds_right"]].to_numpy()).mean()),
        }
        if "airborne" in df:
            air = df["airborne"].to_numpy() > 0.5
            stand_mm = self.body.morphology.stand_height_m * 1e3
            xyz = df[["x_mm", "y_mm", "z_mm"]].to_numpy()
            seg3d = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
            m["airborne_time_s"] = float(air.mean() * dur) if len(air) else 0.0
            m["n_takeoffs"] = int(self.n_takeoffs)
            m["n_touchdowns"] = int(self.n_touchdowns)
            m["max_altitude_mm"] = float(df["z_mm"].max() - stand_mm)
            m["distance_flown_mm"] = float(seg3d[air[1:]].sum()) if len(seg3d) else 0.0
            if "speed_3d_mm_s" in df:
                m["max_speed_3d_mm_s"] = float(df["speed_3d_mm_s"].max(skipna=True))
            if "behavior" in df:
                m["time_feeding_s"] = float((df["behavior"] == "feeding").mean() * dur)
        for src in self.config.arena.odor_sources:
            d = np.hypot(xy[:, 0] - src.x_mm, xy[:, 1] - src.y_mm)
            m[f"min_dist_{src.valence}_source_mm"] = float(d.min())
            m[f"final_dist_{src.valence}_source_mm"] = float(d[-1])
            m[f"initial_dist_{src.valence}_source_mm"] = float(d[0])
        if self.brain is not None:
            m["brain_spikes_total"] = len(self.brain.spikes)
            for k in self.decoder.rate:
                col = f"rate_{k}"
                if col in df:
                    m[f"mean_readout_hz_{k}"] = float(df[col].mean())
        return m

    def provenance(self) -> dict:
        prov = {
            "kind": "virtual_fly_session",
            "id": self.id,
            "created_at": self.created_at,
            "config": json.loads(self.config.model_dump_json()),
            "controller": self.config.controller,
            "components": {
                "physics": "MuJoCo via FlyGym 2.1.1 (authoritative body state)",
                "body": "NeuroMechFly v2 official model "
                "(make_locomotion_fly: 42 actuated leg DoFs)",
                "motor_controller": "FlyGym HybridTurningController (CPG + sensory feedback "
                "rules) - external algorithm, not connectome",
                "flight": "FlyMind reduced-order flight model: wingbeat-averaged quasi-steady "
                "blade-element aerodynamics (Dickinson et al. 1999 coefficients), 6-DoF rigid "
                "body, cascaded flight controller. Not part of FlyGym or the connectome. "
                "Omits rotational circulation, added mass, wake capture, ground effect, wind, "
                "haltere feedback. See docs/scientific/flight.md",
                "behaviour_policy": (
                    "scripted fly-like policy (demonstration, not connectome)"
                    if self.policy is not None
                    else None
                ),
                "neural_model": None
                if self.brain is None
                else f"LIF network on {self.brain.config.dataset_id} ({self.brain.network.mode}, "
                f"{self.brain.network.n} neurons)",
                "bridge": None if self.bridge is None else self.bridge.model_dump(),
                "odor_field": "FlyMind analytic model I = peak / (1 + (d/scale)^2)",
            },
            "missing_groups": getattr(self, "missing_groups", []),
            "evidence": (
                "demonstration"
                if self.config.controller in ("baseline", "autonomous")
                else self.bridge.evidence
                if self.bridge
                else "simulation_output"
            ),
            "runtime": runtime_provenance(),
            "actions": self.actions,
        }
        if self.bridge is not None and self.bridge.tonic_forward > 0:
            prov["scripted_drive_warning"] = (
                f"tonic_forward={self.bridge.tonic_forward}: part of the locomotion is scripted"
            )
        if self.config.controller == "neural" and (self.mode == "fly" or self.n_takeoffs):
            prov["scripted_flight_warning"] = (
                "Wing flapping, hover stabilisation and altitude hold are provided by FlyMind's "
                "flight controller; only the forward and turning commands come from the neural "
                "readout."
            )
        return prov

    def save(self, root: Path | None = None) -> Path:
        name = validate_identifier(f"fly_{self.id}", "session id")
        out = safe_join(root or experiments_dir(), name)
        out.mkdir(parents=True, exist_ok=True)
        self.trajectory().to_parquet(out / "trajectory.parquet", index=False)
        if self.rec_joints:
            dof = [str(d) for d in self.body.fly.get_jointdofs_order()]
            pd.DataFrame(
                np.vstack(self.rec_joints), columns=dof[: self.rec_joints[0].shape[0]]
            ).assign(t_s=[r["t_s"] for r in self.rec_rows]).to_parquet(
                out / "joints.parquet", index=False
            )
        if self.rec_frames:
            np.savez_compressed(
                out / "frames.npz", t_s=np.array(self.rec_frame_t), poses=np.stack(self.rec_frames)
            )
        if self.brain is not None:
            self.brain.spikes_frame().to_parquet(out / "spikes.parquet", index=False)
        record = {
            **self.provenance(),
            "metrics": self.metrics(),
            "wall_s": self.wall_s,
            "sim_wall_ratio": (self.body.t_s / self.wall_s) if self.wall_s else None,
        }
        (out / "record.json").write_text(json.dumps(record, indent=2, default=_json) + "\n")
        return out

    def summary(self) -> dict:
        return {
            "id": self.id,
            "label": self.config.label,
            "status": self.status,
            "error": self.error,
            "controller": self.config.controller,
            "arena": self.config.arena.model_dump(),
            "t_s": self.body.t_s,
            "duration_s": self.config.duration_s,
            "wall_s": self.wall_s,
            "sim_wall_ratio": (self.body.t_s / self.wall_s) if self.wall_s else None,
            "vision": self.body.vision,
            "vision_error": self.body.vision_error,
            "brain_session_id": self.brain.id if self.brain else None,
            "bridge": self.bridge.model_dump() if self.bridge else None,
            "missing_groups": getattr(self, "missing_groups", []),
            "baseline": self.config.baseline.model_dump(),
            "state": self.last_state,
            "n_geoms": len(self.body.mesh_geoms),
            "evidence": "demonstration"
            if self.config.controller in ("baseline", "autonomous")
            else (self.bridge.evidence if self.bridge else "simulation_output"),
            "locomotion": self.loco.state,
            "mode": self.mode,
            "altitude_mm": self.altitude_mm,
            "behavior": self.intent.label,
            "wing_display_hz": self.wing_display_hz,
        }


def _json(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


class FlySessionManager:
    def __init__(self, max_sessions: int = 3):
        self.max_sessions = max_sessions
        self._sessions: dict[str, FlySession] = {}
        self._lock = threading.Lock()

    def create(self, config: FlySessionConfig, brain_factory=None) -> FlySession:
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                for sid, s in list(self._sessions.items()):
                    if s.status != "running":
                        s.stop()
                        del self._sessions[sid]
                        break
                else:
                    raise RuntimeError("too many running fly sessions")
        s = FlySession(config, brain_factory)
        with self._lock:
            self._sessions[s.id] = s
        return s

    def get(self, sid: str) -> FlySession:
        try:
            return self._sessions[sid]
        except KeyError:
            raise KeyError(f"no fly session {sid}") from None

    def list(self) -> list[FlySession]:
        return list(self._sessions.values())

    def delete(self, sid: str) -> None:
        with self._lock:
            s = self._sessions.pop(sid, None)
        if s:
            s.stop()

    def shutdown(self) -> None:
        for s in self.list():
            s.stop()
