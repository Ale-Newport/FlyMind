"""Locomotion state machine and a scripted, fly-like autonomous behaviour policy.

Two layers sit between a high-level *intent* and the body:

* :class:`LocomotionController` decides whether the body walks (FlyGym physics) or flies
  (:class:`~flymind.embodiment.flight.FlightSim`) and runs the transitions
  ``ground -> takeoff -> flight -> landing -> ground``. A fly cannot walk and fly at the same
  time, so the intent only names the desired mode; the controller makes the transition coherent
  (wings unfold, legs fold with altitude, landing is a slow descent with the wings stopping
  after touchdown).
* :class:`AutonomousPolicy` is a *demonstration* policy, not a model of the connectome. It
  strings together behaviours known from *Drosophila* (walking bouts and pauses, take-off,
  straight flight segments separated by body saccades, odour tracking, landing on food,
  feeding, obstacle and aversive-odour avoidance) from the sensors the body actually exposes.
  Every decision is reported as a ``label`` so the interface can show what the fly is doing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from flymind.embodiment.arena import ArenaConfig
from flymind.embodiment.body import FlyBody
from flymind.embodiment.flight import FlightCommand, wrap_pi
from flymind.embodiment.flight_pose import smoothstep

Mode = Literal["walk", "fly"]
LocoState = Literal["ground", "takeoff", "flight", "landing"]

ANTENNAL_GAIN = 30.0  # rad per unit normalised L-R contrast (a ~0.02 contrast is typical)
V_MAX_FLIGHT = 0.20  # m/s at forward drive 1.2 (D. melanogaster cruises at 0.1-0.5 m/s)
YAW_RATE_MAX = 5.0  # rad/s at turn = 1 (sustained turns; saccades are faster, set by heading)
BACKWARD_FACTOR = 0.35


@dataclass
class Intent:
    """What the fly 'wants' this instant, before the locomotion mode turns it into motion."""

    forward: float = 0.0  # descending drive, -1.2 .. 1.2
    turn: float = 0.0  # -1 .. 1, positive steers left
    locomotion: Mode = "walk"
    altitude_mm: float = 8.0  # thorax height while flying
    heading: float | None = None  # absolute heading target (rad); overrides ``turn`` in flight
    label: str = "manual"


def command_to_ds(forward: float, turn: float, turn_gain: float = 0.8) -> np.ndarray:
    """FlyGym's two-value descending command from (forward, turn)."""
    dl = np.clip(forward - turn_gain * 1.2 * turn, -1.2, 1.2)
    dr = np.clip(forward + turn_gain * 1.2 * turn, -1.2, 1.2)
    return np.array([dl, dr])


class LocomotionController:
    """Walk/fly state machine around a :class:`FlyBody`."""

    TAKEOFF_DONE_MM = 2.5  # height above the standing height at which take-off is complete

    def __init__(self, body: FlyBody):
        self.body = body
        self.reset()

    def reset(self) -> None:
        self.state: LocoState = "ground"
        self.events: list[str] = []
        self._winding_down = False

    @property
    def airborne(self) -> bool:
        return self.state != "ground"

    def advance(self, intent: Intent, ds: np.ndarray, k_steps: int, dt_s: float) -> list[str]:
        """Run one bridge interval. Returns transition events (``takeoff``, ``touchdown``...)."""
        b = self.body
        events: list[str] = []
        want_fly = intent.locomotion == "fly"
        if self.state == "ground":
            if want_fly:
                b.enter_flight()
                self.state = "takeoff"
                events.append("takeoff")
        elif self.state in ("takeoff", "flight") and not want_fly:
            self.state = "landing"
            self._winding_down = False
            events.append("landing")
        elif self.state == "landing" and want_fly and not self._winding_down:
            self.state = "flight"
            events.append("go-around")

        if self.state == "ground":
            for _ in range(k_steps):
                b.step(ds)
            return events

        cmd = self._flight_command(intent)
        b.fly_step(cmd, k_steps * dt_s)
        fl = b.flight
        height_mm = (fl.altitude() - b.morphology.stand_height_m) * 1e3
        if self.state == "takeoff" and height_mm > self.TAKEOFF_DONE_MM:
            self.state = "flight"
        if self.state == "landing":
            if fl.state.on_ground:
                self._winding_down = True
            if self._winding_down and not fl.state.engaged:
                b.land()
                self.state = "ground"
                self._winding_down = False
                events.append("touchdown")
        return events

    def _flight_command(self, intent: Intent) -> FlightCommand:
        b = self.body
        fl = b.flight
        stand = b.morphology.stand_height_m
        height = fl.altitude() - stand
        fwd = float(np.clip(intent.forward, -1.2, 1.2)) / 1.2
        speed = fwd * V_MAX_FLIGHT if fwd >= 0 else fwd * V_MAX_FLIGHT * BACKWARD_FACTOR
        # no skating along the ground while the legs are still pushing off
        speed *= 0.25 + 0.75 * smoothstep(height / 2.5e-3)
        cmd = FlightCommand(
            speed=speed,
            yaw_rate=float(np.clip(intent.turn, -1, 1)) * YAW_RATE_MAX,
            heading=intent.heading,
            altitude=max(intent.altitude_mm, 2.0) * 1e-3,
        )
        if self.state == "landing":
            cmd.altitude = stand - 0.6e-3
            cmd.speed = float(np.clip(speed, -0.02, 0.035))
            cmd.descend_limit = 0.02 + 0.13 * smoothstep(height / 5e-3)
            cmd.wings = not self._winding_down
        return cmd


# --------------------------------------------------------------------- autonomous policy
@dataclass
class Observation:
    t_s: float
    x_mm: float
    y_mm: float
    z_mm: float
    heading_rad: float
    sensors: dict[str, float]
    airborne: bool
    speed_mm_s: float = 0.0


@dataclass
class _Params:
    decision_hz: float = 20.0
    odor_threshold: float = 0.04  # ~40 mm from a source of scale 8 mm
    land_odor: float = 0.5  # attractive odour at which a flying fly lands (~8 mm from the source)
    saccade_rate_hz: float = 1.1
    saccade_sd_deg: float = 55.0
    flight_min_s: float = 3.0
    flight_land_hazard_hz: float = 0.12
    walk_to_fly_hazard_hz: float = 0.22
    walk_min_s: float = 2.5
    feed_s: tuple[float, float] = (3.5, 7.0)
    sated_s: float = 25.0
    arena_radius_mm: float = 110.0
    altitude_mm: tuple[float, float] = (5.5, 13.0)
    cruise: tuple[float, float] = (0.55, 0.95)


class AutonomousPolicy:
    """A fly-like forager built from documented behaviours (demonstration, not connectome)."""

    def __init__(self, arena: ArenaConfig, seed: int = 0, params: _Params | None = None):
        self.arena = arena
        self.p = params or _Params()
        self.seed = seed
        self.reset()

    def reset(self) -> None:
        self.rng = np.random.default_rng(np.random.SeedSequence([self.seed, 0xF1E5]))
        self.mode = "rest"
        self.mode_t0 = 0.0
        self.mode_dur = 0.8
        self.target: float | None = None
        self.altitude_mm = 8.0
        self.cruise = 0.8
        self.sated_until = -1.0
        self.next_decision = 0.0
        self.next_saccade = 1.0
        self.next_wander = 1.0
        self.next_alt = 2.0
        self.prev_odor = 0.0
        self.d_odor = 0.0
        self.flight_t0 = 0.0
        self.avoid_until = -1.0
        self.avoid_dir = 1.0
        self.intent = Intent(label="resting")
        self.was_airborne = False
        self.log: list[tuple[float, str]] = []

    # ------------------------------------------------------------------ helpers
    def _set(self, mode: str, t: float, dur: float | None = None) -> None:
        """Enter ``mode``. Re-entering the current mode keeps its timer (unless ``dur`` given)."""
        if mode != self.mode or dur is not None:
            if mode != self.mode:
                self.log.append((t, mode))
            self.mode = mode
            self.mode_t0 = t
            self.mode_dur = dur if dur is not None else 0.0

    def _elapsed(self, t: float) -> float:
        return t - self.mode_t0

    def _steer_walk(self, heading: float) -> float:
        if self.target is None:
            return 0.0
        return float(np.clip(0.9 * wrap_pi(self.target - heading), -1.0, 1.0))

    def _obstacle_ahead(self, o: Observation, reach_mm: float) -> float | None:
        """Distance (mm) to the nearest obstacle top ahead (a stand-in for looming detection)."""
        best = None
        cx, cy = math.cos(o.heading_rad), math.sin(o.heading_rad)
        for ob in self.arena.obstacles:
            if ob.height_mm + 1.5 < o.z_mm:
                continue
            dx, dy = ob.x_mm - o.x_mm, ob.y_mm - o.y_mm
            ahead = dx * cx + dy * cy
            side = -dx * cy + dy * cx
            radius = max(ob.half_x_mm, ob.half_y_mm) + 1.0
            if 0 < ahead < reach_mm + radius and abs(side) < radius + 1.5:
                d = ahead - radius
                best = d if best is None else min(best, d)
        return best

    # --------------------------------------------------------------------- step
    def step(self, o: Observation) -> Intent:
        if o.t_s < self.next_decision:
            return self._refresh(o)
        self.next_decision = o.t_s + 1.0 / self.p.decision_hz
        dt = 1.0 / self.p.decision_hz
        s = o.sensors
        al, ar = s.get("odor_attractive_left", 0.0), s.get("odor_attractive_right", 0.0)
        vl, vr = s.get("odor_aversive_left", 0.0), s.get("odor_aversive_right", 0.0)
        odor = 0.5 * (al + ar)  # concentration at the antennae (single-antenna equivalent)
        self.d_odor += 0.25 * (((odor - self.prev_odor) / dt) - self.d_odor)
        self.prev_odor = odor
        hungry = o.t_s >= self.sated_until
        aversive = max(vl, vr)
        if self.target is None:
            self.target = o.heading_rad
        if o.airborne != self.was_airborne:
            self.was_airborne = o.airborne
            if o.airborne:
                self.flight_t0 = o.t_s
                self.altitude_mm = float(np.clip(o.z_mm + 6.0, *self.p.altitude_mm))
        t = o.t_s

        # --- feeding: stand on the food patch
        if self.mode == "feed":
            if self._elapsed(t) >= self.mode_dur:
                self._set("leave", t, 2.0)
                self.target = wrap_pi(o.heading_rad + math.pi + self.rng.normal(0, 0.5))
            else:
                self.intent = Intent(0.0, 0.0, "walk", label="feeding")
                return self.intent
        if not o.airborne and s.get("on_food", 0.0) > 0.5 and hungry and self.mode != "leave":
            self._set("feed", t, float(self.rng.uniform(*self.p.feed_s)))
            self.sated_until = t + self.mode_dur + self.p.sated_s
            self.intent = Intent(0.0, 0.0, "walk", label="feeding")
            return self.intent

        # --- obstacle contact on the ground: back off and turn away
        contact = s.get("contact_left", 0.0) + s.get("contact_right", 0.0)
        if contact > 0 and t >= self.avoid_until:
            self.avoid_until = t + 0.6
            self.avoid_dir = (
                -1.0 if s.get("contact_left", 0.0) > s.get("contact_right", 0.0) else 1.0
            )
            self.target = wrap_pi(
                o.heading_rad + self.avoid_dir * (math.pi / 2 + self.rng.uniform(0, 0.8))
            )
        if t < self.avoid_until:
            self.intent = Intent(
                -0.7 if not o.airborne else 0.2,
                self.avoid_dir * 0.8 if not o.airborne else 0.0,
                "fly" if o.airborne else "walk",
                self.altitude_mm,
                heading=self.target if o.airborne else None,
                label="avoiding obstacle",
            )
            return self.intent

        # --- aversive odour: flee, taking off if standing
        if aversive > 0.18:
            away = -1.0 if vl > vr else 1.0  # steer away from the stronger side
            if t >= self.next_saccade:
                self.target = wrap_pi(o.heading_rad + away * self.rng.uniform(0.7, 1.4))
                self.next_saccade = t + 0.5
            if not o.airborne:
                self.intent = Intent(
                    1.0, self._steer_walk(o.heading_rad), "fly", 9.0, label="fleeing aversive odour"
                )
            else:
                self.intent = Intent(
                    1.0, 0.0, "fly", self.altitude_mm, self.target, "fleeing aversive odour"
                )
            return self.intent

        # --- boundary: stay within the arena
        r = math.hypot(o.x_mm, o.y_mm)
        returning = r > self.p.arena_radius_mm
        if returning:
            home = math.atan2(-o.y_mm, -o.x_mm)
            if abs(wrap_pi(home - (self.target or 0.0))) > 0.6:
                self.target = wrap_pi(home + self.rng.normal(0, 0.25))

        tracking = hungry and odor > self.p.odor_threshold and not returning
        if o.airborne:
            return self._fly(o, t, dt, al, ar, odor, tracking, returning)
        return self._ground(o, t, dt, al, ar, odor, tracking, returning)

    def _refresh(self, o: Observation) -> Intent:
        """Between decisions keep the last intent (heading targets persist)."""
        return self.intent

    # -------------------------------------------------------------------- ground
    def _ground(self, o, t, dt, al, ar, odor, tracking, returning) -> Intent:
        if self.mode == "leave":
            if self._elapsed(t) >= self.mode_dur:
                self._set("walk", t)
            self.intent = Intent(
                1.0, self._steer_walk(o.heading_rad), "walk", label="leaving the food"
            )
            return self.intent
        if tracking:
            self._set("track", t)
            bias = (al - ar) / (al + ar + 1e-6)
            self.target = wrap_pi(o.heading_rad + float(np.clip(ANTENNAL_GAIN * bias, -1.2, 1.2)))
            label = "tracking odour on foot"
            # walked past the source (odour now falling): turn back, a local search
            if odor > 0.5 and self.d_odor < -0.03 and t >= self.next_saccade:
                self.target = wrap_pi(o.heading_rad + math.pi + float(self.rng.normal(0, 0.4)))
                self.next_saccade = t + 1.8
                label = "searching near the odour source"
            if t < self.next_saccade - 1.2:
                label = "searching near the odour source"
                steer = 0.9 * wrap_pi(self.target - o.heading_rad)
            else:
                steer = 0.9 * wrap_pi(self.target - o.heading_rad)
            speed = 1.0 if odor < 0.45 else 0.45  # slow down close to the source
            self.intent = Intent(speed, float(np.clip(steer, -1, 1)), "walk", label=label)
            return self.intent
        if self.mode not in ("rest", "walk"):
            self._set("rest", t, float(self.rng.exponential(0.8)) + 0.3)
        if self.mode == "rest":
            self.intent = Intent(0.0, 0.0, "walk", label="resting")
            if self._elapsed(t) >= self.mode_dur:
                self._set("walk", t)
                self.next_wander = t + float(self.rng.uniform(0.4, 1.2))
            return self.intent
        # walking bout
        if t >= self.next_wander:
            self.target = wrap_pi(self.target + float(self.rng.normal(0, 0.55)))
            self.next_wander = t + float(self.rng.uniform(0.4, 1.4))
        label = "returning to the arena" if returning else "walking"
        ahead = self._obstacle_ahead(o, 6.0)
        if ahead is not None and ahead < 3.0:
            self.target = wrap_pi(o.heading_rad + float(self.rng.choice([-1, 1])) * 1.0)
        walked = self._elapsed(t)
        take_off = (
            walked > self.p.walk_min_s and self.rng.random() < self.p.walk_to_fly_hazard_hz * dt
        )
        if take_off:
            self._set("fly", t)
            self.flight_t0 = t
            self.cruise = float(self.rng.uniform(*self.p.cruise))
            self.intent = Intent(0.5, 0.0, "fly", self.altitude_mm, label="taking off")
            return self.intent
        if walked > float(self.rng.uniform(4, 9)) and self.rng.random() < 0.3 * dt:
            self._set("rest", t, float(self.rng.exponential(0.8)) + 0.3)
        self.intent = Intent(0.85, self._steer_walk(o.heading_rad), "walk", label=label)
        return self.intent

    # -------------------------------------------------------------------- flight
    def _fly(self, o, t, dt, al, ar, odor, tracking, returning) -> Intent:
        if self.mode not in ("fly", "fly_track", "land"):
            self._set("fly", t)
            self.flight_t0 = t
        label = "flying"
        speed = self.cruise
        if self.mode == "land":
            self.intent = Intent(0.0, 0.0, "walk", self.altitude_mm, None, "landing")
            return self.intent
        if tracking:
            self._set("fly_track", t) if self.mode != "fly_track" else None
            bias = (al - ar) / (al + ar + 1e-6)
            # klinotaxis: steer toward the stronger antenna; shed speed as the odour grows
            self.target = wrap_pi(o.heading_rad + float(np.clip(ANTENNAL_GAIN * bias, -1.2, 1.2)))
            speed = self.cruise * (1.0 - 0.85 * float(np.clip((odor - 0.1) / 0.4, 0, 1)))
            label = "tracking odour in flight"
            # lose the plume: saccade more often (dC/dt < 0), less when climbing the gradient
            rate = self.p.saccade_rate_hz * (0.25 if self.d_odor > 0 else 2.2)
            if t >= self.next_saccade:
                self.target = wrap_pi(
                    self.target + float(self.rng.normal(0, math.radians(self.p.saccade_sd_deg)))
                )
                self.next_saccade = t + float(self.rng.exponential(1.0 / rate)) + 0.25
            if odor >= self.p.land_odor:
                self._set("land", t)
                self.intent = Intent(0.0, 0.0, "walk", self.altitude_mm, None, "landing on food")
                return self.intent
        else:
            if self.mode == "fly_track":
                self._set("fly", t)
            if t >= self.next_saccade and not returning:
                amp = float(
                    np.clip(self.rng.normal(0, math.radians(self.p.saccade_sd_deg)), -1.9, 1.9)
                )
                self.target = wrap_pi(o.heading_rad + amp)
                self.next_saccade = (
                    t + float(self.rng.exponential(1.0 / self.p.saccade_rate_hz)) + 0.3
                )
                label = "saccade"
            if returning:
                label = "returning to the arena"
            if t >= self.next_alt:
                self.altitude_mm = float(
                    np.clip(self.altitude_mm + self.rng.normal(0, 2.0), *self.p.altitude_mm)
                )
                self.next_alt = t + float(self.rng.uniform(1.0, 2.5))
            if (
                t - self.flight_t0 > self.p.flight_min_s
                and self.rng.random() < self.p.flight_land_hazard_hz * dt
            ):
                self._set("land", t)
                self.intent = Intent(0.3, 0.0, "walk", self.altitude_mm, None, "landing")
                return self.intent
        ahead = self._obstacle_ahead(o, 12.0)
        alt = self.altitude_mm
        if ahead is not None:
            top = max(ob.height_mm for ob in self.arena.obstacles)
            if o.z_mm < top + 3.5:
                alt = max(alt, top + 5.0)  # climb over low obstacles
                label = "climbing over an obstacle"
        self.intent = Intent(speed, 0.0, "fly", alt, self.target, label)
        return self.intent
