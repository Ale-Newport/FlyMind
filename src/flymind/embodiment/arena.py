"""Virtual environments for the NeuroMechFly body (FlyGym 2.x / MuJoCo).

Physical objects (ground, obstacles) are real MuJoCo collision geometry. Visual
objects (light pillars, food patches) are rendered by MuJoCo and therefore seen by
the fly's compound-eye cameras. Odour is not simulated by FlyGym 2.x, so FlyMind
models a static odour field analytically (see :func:`odor_intensity`), following
the approach of FlyGym 1.x's OdorArena (intensity decaying with distance from
point sources). The odour field is a modelling assumption, not fluid dynamics.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

ArenaKind = Literal["empty", "food", "obstacle", "light", "experimental"]


class OdorSource(BaseModel):
    x_mm: float
    y_mm: float
    peak: float = Field(1.0, ge=0, le=10, description="intensity at the source (a.u.)")
    scale_mm: float = Field(8.0, gt=0, le=200, description="distance at which intensity halves")
    valence: Literal["attractive", "aversive", "neutral"] = "attractive"
    label: str = ""


class Obstacle(BaseModel):
    x_mm: float
    y_mm: float
    half_x_mm: float = Field(0.5, gt=0, le=50)
    half_y_mm: float = Field(3.0, gt=0, le=50)
    height_mm: float = Field(2.0, gt=0, le=20)
    yaw_deg: float = 0.0
    label: str = ""


class LightSource(BaseModel):
    """A bright vertical pillar (an emissive visual object seen by the compound eyes)."""

    x_mm: float
    y_mm: float
    radius_mm: float = Field(2.0, gt=0, le=30)
    height_mm: float = Field(12.0, gt=0, le=100)
    intensity: float = Field(1.0, ge=0, le=1)
    label: str = ""


class FoodPatch(BaseModel):
    x_mm: float
    y_mm: float
    radius_mm: float = Field(2.0, gt=0, le=30)
    label: str = "sucrose"


class ArenaConfig(BaseModel):
    kind: ArenaKind = "empty"
    name: str = "Empty arena"
    description: str = ""
    odor_sources: list[OdorSource] = Field(default_factory=list, max_length=8)
    obstacles: list[Obstacle] = Field(default_factory=list, max_length=32)
    lights: list[LightSource] = Field(default_factory=list, max_length=8)
    food: list[FoodPatch] = Field(default_factory=list, max_length=8)
    ambient: float = Field(0.6, ge=0, le=1, description="scene brightness (headlight)")
    spawn_x_mm: float = 0.0
    spawn_y_mm: float = 0.0
    spawn_heading_deg: float = 0.0


def arena_preset(kind: ArenaKind) -> ArenaConfig:
    if kind == "empty":
        return ArenaConfig(
            kind="empty",
            name="Empty arena",
            description="Flat ground; basic locomotion and neural inspection.",
        )
    if kind == "food":
        return ArenaConfig(
            kind="food",
            name="Food arena",
            description="A food patch emitting an attractive odour, ahead and to the left.",
            odor_sources=[
                OdorSource(
                    x_mm=18,
                    y_mm=8,
                    peak=1.0,
                    scale_mm=8.0,
                    valence="attractive",
                    label="vinegar-like",
                )
            ],
            food=[FoodPatch(x_mm=18, y_mm=8, radius_mm=2.5)],
        )
    if kind == "obstacle":
        return ArenaConfig(
            kind="obstacle",
            name="Obstacle arena",
            description="A wall across the walking direction and two blocks.",
            obstacles=[
                Obstacle(x_mm=7, y_mm=0, half_x_mm=0.5, half_y_mm=5, height_mm=2.0, label="wall"),
                Obstacle(
                    x_mm=14, y_mm=7, half_x_mm=1.5, half_y_mm=1.5, height_mm=2.0, label="block"
                ),
                Obstacle(
                    x_mm=14, y_mm=-7, half_x_mm=1.5, half_y_mm=1.5, height_mm=2.0, label="block"
                ),
            ],
        )
    if kind == "light":
        return ArenaConfig(
            kind="light",
            name="Light arena",
            description="Dim arena with a bright pillar ahead and to the right.",
            lights=[LightSource(x_mm=20, y_mm=-10, radius_mm=3, height_mm=15, intensity=1.0)],
            ambient=0.15,
        )
    return ArenaConfig(
        kind="experimental",
        name="Experimental arena",
        description="Customisable: place odour sources, obstacles, lights and food.",
        odor_sources=[OdorSource(x_mm=20, y_mm=-6, valence="aversive", label="geosmin-like")],
        obstacles=[Obstacle(x_mm=10, y_mm=6, half_x_mm=1, half_y_mm=1, label="block")],
        lights=[LightSource(x_mm=25, y_mm=12, radius_mm=2)],
        food=[FoodPatch(x_mm=25, y_mm=0)],
    )


def odor_intensity(sources: list[OdorSource], xy: np.ndarray) -> dict[str, float]:
    """Summed intensity per valence at planar position ``xy`` (mm).

    I(d) = peak / (1 + (d / scale)^2): smooth, finite at the source, inverse-square
    far away (cf. FlyGym 1.x OdorArena's power-law diffusion function).
    """
    out = {"attractive": 0.0, "aversive": 0.0, "neutral": 0.0}
    for s in sources:
        d = math.hypot(float(xy[0]) - s.x_mm, float(xy[1]) - s.y_mm)
        out[s.valence] += s.peak / (1.0 + (d / s.scale_mm) ** 2)
    return out


def odor_grid(sources: list[OdorSource], extent_mm: float = 40.0, n: int = 64) -> dict:
    """Sampled odour field for visualisation."""
    xs = np.linspace(-extent_mm / 2, extent_mm * 1.5, n)
    ys = np.linspace(-extent_mm, extent_mm, n)
    grid = {"attractive": np.zeros((n, n)), "aversive": np.zeros((n, n))}
    for s in sources:
        if s.valence == "neutral":
            continue
        dx = xs[None, :] - s.x_mm
        dy = ys[:, None] - s.y_mm
        grid[s.valence] += s.peak / (1.0 + (dx**2 + dy**2) / s.scale_mm**2)
    return {
        "x_mm": xs.tolist(),
        "y_mm": ys.tolist(),
        "attractive": grid["attractive"].round(4).tolist(),
        "aversive": grid["aversive"].round(4).tolist(),
    }


def build_world(arena: ArenaConfig):
    """FlatGroundWorld + obstacles (collidable, registered as ground geoms) + visuals."""
    from flygym.compose import FlatGroundWorld
    from flygym.utils.mjcf import GEOM_TYPES, add_material

    world = FlatGroundWorld(name="flymind_arena", half_size=300)
    spec = world.mjcf_root
    amb = float(arena.ambient)
    spec.visual.headlight.ambient = [0.3 * amb] * 3
    spec.visual.headlight.diffuse = [0.7 * amb] * 3
    for k, ob in enumerate(arena.obstacles):
        yaw = math.radians(ob.yaw_deg)
        geom = spec.worldbody.add_geom(
            type=GEOM_TYPES["box"],
            name=f"obstacle_{k}",
            size=(ob.half_x_mm, ob.half_y_mm, ob.height_mm / 2),
            pos=(ob.x_mm, ob.y_mm, ob.height_mm / 2),
            quat=(math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)),
            rgba=(0.55, 0.42, 0.3, 1.0),
            contype=0,
            conaffinity=0,
        )
        world.ground_geoms.append(geom)
    for k, li in enumerate(arena.lights):
        add_material(
            spec,
            name=f"light_mat_{k}",
            emission=float(li.intensity) * 2.0,
            rgba=(1.0, 1.0, 0.92, 1.0),
        )
        spec.worldbody.add_geom(
            type=GEOM_TYPES["cylinder"],
            name=f"light_{k}",
            size=(li.radius_mm, li.height_mm / 2, 0),
            pos=(li.x_mm, li.y_mm, li.height_mm / 2),
            material=f"light_mat_{k}",
            contype=0,
            conaffinity=0,
        )
    for k, fd in enumerate(arena.food):
        spec.worldbody.add_geom(
            type=GEOM_TYPES["cylinder"],
            name=f"food_{k}",
            size=(fd.radius_mm, 0.02, 0),
            pos=(fd.x_mm, fd.y_mm, 0.02),
            rgba=(0.95, 0.75, 0.2, 1.0),
            contype=0,
            conaffinity=0,
        )
    for k, od in enumerate(arena.odor_sources):
        # small marker in geom group 1 (ignored by the eye renderer, visible to users)
        spec.worldbody.add_geom(
            type=GEOM_TYPES["sphere"],
            name=f"odor_{k}",
            size=(0.4, 0, 0),
            pos=(od.x_mm, od.y_mm, 1.5),
            group=1,
            rgba=(0.3, 0.9, 0.5, 0.6) if od.valence == "attractive" else (0.9, 0.3, 0.3, 0.6),
            contype=0,
            conaffinity=0,
        )
    return world
