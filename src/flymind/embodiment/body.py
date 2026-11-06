"""The NeuroMechFly body in a FlyMind arena: physics, sensors, locomotion controller.

Physics, body geometry and the walking controller are FlyGym 2.x components
(NeuroMechFly v2, Wang-Chen et al. 2024, Nature Methods 21:2353; Apache-2.0):

* ``make_locomotion_fly`` - official NeuroMechFly body with position-actuated legs
  (42 DoFs) and leg adhesion;
* ``HybridTurningController`` - CPG + sensory-feedback rule controller that turns a
  two-value descending command into joint targets (an external motor-control
  algorithm, not part of the connectome model).

The MuJoCo state is authoritative while walking: the browser only renders the geom poses
streamed from here. FlyGym has no flight, so while airborne the body is integrated by
:class:`flymind.embodiment.flight.FlightSim` (a FlyMind model) and its pose is written into
the MuJoCo root joint, so sensors, recording and rendering use one code path.
"""

from __future__ import annotations

import math

import mujoco as mj
import numpy as np
from scipy.spatial.transform import Rotation

from flymind.embodiment.arena import ArenaConfig, build_world, odor_intensity
from flymind.embodiment.flight import (
    MM,
    Box,
    FlightCommand,
    FlightSim,
    Morphology,
    mat_to_quat,
    wing_frame,  # noqa: F401  (re-exported for tests)
)
from flymind.embodiment.flight_pose import (
    TUCK_POSE,
    smoothstep,
    wing_display_rotation,
    wing_rest_frame,
)

FLY_NAME = "fly"
_ANTENNA = ("l_funiculus", "r_funiculus")


class FlyBody:
    def __init__(self, arena: ArenaConfig, vision: bool = False, seed: int = 0):
        from flygym import Simulation
        from flygym.anatomy import ContactBodiesPreset
        from flygym.utils.math import Rotation3D
        from flygym_demo.complex_terrain import (
            HybridTurningController,
            PreprogrammedSteps,
            make_locomotion_fly,
        )

        self.arena = arena
        self.vision = vision
        self.seed = seed
        fly = make_locomotion_fly(name=FLY_NAME, add_adhesion=True, colorize=True)
        if vision:
            fly.add_vision()
        world = build_world(arena)
        yaw = math.radians(arena.spawn_heading_deg)
        world.add_fly(
            fly,
            [arena.spawn_x_mm, arena.spawn_y_mm, 0.8],
            Rotation3D("quat", [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]),
            bodysegs_with_ground_contact=ContactBodiesPreset.LEGS_THORAX_ABDOMEN_HEAD,
            add_ground_contact_sensors=False,
        )
        self.fly = fly
        self.sim = Simulation(world)
        self.model, self.data = self.sim.mj_model, self.sim.mj_data
        self.dt_s = float(self.sim.timestep)
        self.preprogrammed = PreprogrammedSteps()
        self.dof_order = fly.get_actuated_jointdofs_order("position")
        self.controller = HybridTurningController(
            timestep=self.sim.timestep,
            preprogrammed_steps=self.preprogrammed,
            output_dof_order=self.dof_order,
        )
        segs = [s.name for s in fly.get_bodysegs_order()]
        self._thorax = segs.index("c_thorax")
        self._antennae = [segs.index(a) for a in _ANTENNA]
        m = self.model
        self.mesh_geoms = np.array(
            [
                i
                for i in range(m.ngeom)
                if m.geom_type[i] == mj.mjtGeom.mjGEOM_MESH
                and (mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, i) or "").startswith(f"{FLY_NAME}/")
            ],
            dtype=np.int64,
        )
        self.obstacle_geoms = np.array(
            [
                i
                for i in range(m.ngeom)
                if (mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, i) or "").startswith("obstacle_")
            ],
            dtype=np.int64,
        )
        fly_bodies = {
            b
            for b in range(m.nbody)
            if (mj.mj_id2name(m, mj.mjtObj.mjOBJ_BODY, b) or "").startswith(f"{FLY_NAME}/")
        }
        self._fly_geom_mask = np.isin(m.geom_bodyid, list(fly_bodies))
        self._init_flight_rig()
        self._luminance = (0.0, 0.0)
        self.vision_error: str | None = None
        self._vision_age = np.inf
        self.reset()

    # ----------------------------------------------------------------- control
    def reset(self) -> None:
        from flygym_demo.complex_terrain import LocomotionAction, apply_locomotion_action

        self.flying = False
        self.flight.reset()
        self.sim.reset()
        self.controller.reset(seed=self.seed)
        apply_locomotion_action(
            self.sim,
            FLY_NAME,
            LocomotionAction(
                joint_angles=self.preprogrammed.default_pose_by_dof_order(self.dof_order),
                adhesion_onoff=np.ones(6, dtype=bool),
            ),
        )
        self.sim.warmup()
        self.t_s = 0.0
        self._prev_xy = self.position()[:2].copy()
        self._vision_age = np.inf

    def step(self, descending: np.ndarray) -> None:
        from flygym_demo.complex_terrain import HybridControllerObservation, apply_locomotion_action

        if self.flying:
            raise RuntimeError("walking step requested while airborne; use fly_step")
        obs = HybridControllerObservation.from_sim(self.sim, FLY_NAME)
        action = self.controller.step(np.asarray(descending, dtype=float), obs)
        apply_locomotion_action(self.sim, FLY_NAME, action)
        self.sim.step()
        self.t_s += self.dt_s
        self._vision_age += self.dt_s

    # ------------------------------------------------------------------- state
    def position(self) -> np.ndarray:
        return np.asarray(self.sim.get_body_positions(FLY_NAME)[self._thorax], dtype=float)

    def heading_rad(self) -> float:
        w, x, y, z = self.sim.get_body_rotations(FLY_NAME)[self._thorax]
        return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))

    def joint_angles(self) -> np.ndarray:
        return np.asarray(self.sim.get_joint_angles(FLY_NAME), dtype=np.float32)

    def geom_poses(self, wing_phase: float | None = None) -> np.ndarray:
        """(n_mesh_geoms, 7) float32: x, y, z, qw, qx, qy, qz in the world frame (mm)."""
        pos = self.data.geom_xpos[self.mesh_geoms].copy()
        mats = self.data.geom_xmat[self.mesh_geoms].reshape(-1, 3, 3).copy()
        if self.flying and self.flight.state.engaged:
            self._pose_wings(pos, mats, self.wing_phase if wing_phase is None else wing_phase)
        q = Rotation.from_matrix(mats).as_quat(scalar_first=True)
        return np.hstack([pos, q]).astype(np.float32)

    # ------------------------------------------------------------------- flight
    def _init_flight_rig(self) -> None:
        m, d = self.model, self.data
        self.flying = False
        self.wing_phase = 0.0
        self.morphology = Morphology()
        self.flight = FlightSim(self.morphology)
        self.flight.obstacles = [
            Box(
                o.x_mm * MM,
                o.y_mm * MM,
                o.half_x_mm * MM,
                o.half_y_mm * MM,
                o.height_mm * MM,
                math.radians(o.yaw_deg),
            )
            for o in self.arena.obstacles
        ]
        names = [
            f"{FLY_NAME}/{dof.parent.name}-{dof.child.name}-{dof.axis.value}"
            for dof in self.dof_order
        ]
        adr = np.array(
            [m.jnt_qposadr[mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, n)] for n in names],
            dtype=np.int64,
        )
        self._leg_adr = adr
        self._leg_tuck = np.array([TUCK_POSE[n.removeprefix(f"{FLY_NAME}/")] for n in names])
        self._leg_walk = np.asarray(
            self.preprogrammed.default_pose_by_dof_order(self.dof_order), dtype=float
        )
        # wing rest frames and hinges in the thorax body frame (mm), from the meshes
        mj.mj_forward(m, d)
        th_p, th_r = d.xpos[1].copy(), d.xmat[1].reshape(3, 3).copy()
        self._wing_rows, self._wing_rest, self._wing_hinge = [], [], []
        self._wing_geom_pos, self._wing_geom_mat = [], []
        com_local_mm = -self.morphology.thorax_from_com_m / MM
        for sigma, gname in ((1.0, "l_wing"), (-1.0, "r_wing")):
            gi = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, f"{FLY_NAME}/{gname}")
            self._wing_rows.append(int(np.nonzero(self.mesh_geoms == gi)[0][0]))
            mid = int(m.geom_dataid[gi])
            va, vn = int(m.mesh_vertadr[mid]), int(m.mesh_vertnum[mid])
            w = d.geom_xpos[gi] + m.mesh_vert[va : va + vn] @ d.geom_xmat[gi].reshape(3, 3).T
            v = (w - th_p) @ th_r
            self._wing_rest.append(wing_rest_frame(v, sigma))
            self._wing_hinge.append(
                (self.morphology.hinge_left_m / MM) * np.array([1.0, sigma, 1.0]) + com_local_mm
            )
            self._wing_geom_pos.append(m.geom_pos[gi].copy())
            self._wing_geom_mat.append(
                Rotation.from_quat(m.geom_quat[gi], scalar_first=True).as_matrix()
            )

    def enter_flight(self) -> None:
        """Take off: initialise the flight model from the walking state."""
        if self.flying:
            return
        d = self.data
        thorax = self.position()
        vel = np.asarray(d.qvel[0:3], dtype=float) * MM  # mm/s -> m/s
        self.flight.reset(thorax * MM, self.heading_rad(), velocity=np.array([vel[0], vel[1], 0.0]))
        self.flying = True
        self.wing_phase = 0.0

    def fly_step(self, cmd: FlightCommand, duration_s: float) -> None:
        """Advance the flight model by ``duration_s`` (1 ms sub-steps) and sync the MuJoCo pose."""
        dt = 1e-3
        n = max(1, int(round(duration_s / dt)))
        for _ in range(n):
            self.flight.step(cmd, dt)
        self.t_s += n * dt
        self._sync_flight_pose()

    def _sync_flight_pose(self) -> None:
        fl = self.flight
        d = self.data
        d.qpos[0:3] = fl.thorax_position() / MM
        d.qpos[3:7] = mat_to_quat(fl.state.R)
        h = (fl.altitude() - self.morphology.stand_height_m) / MM
        tuck = smoothstep((h - 0.6) / 2.0)
        d.qpos[self._leg_adr] = self._leg_walk + tuck * (self._leg_tuck - self._leg_walk)
        mj.mj_kinematics(self.model, d)

    def _pose_wings(self, pos: np.ndarray, mats: np.ndarray, phase: float) -> None:
        fl = self.flight
        root_r = self.data.xmat[1].reshape(3, 3)
        root_p = self.data.xpos[1]
        for side, sigma in ((0, 1.0), (1, -1.0)):
            rw = wing_display_rotation(
                self._wing_rest[side], sigma, fl.state.wing, side, fl.state.beta, phase
            )
            hinge = self._wing_hinge[side]
            p_local = hinge + rw @ (self._wing_geom_pos[side] - hinge)
            r_local = rw @ self._wing_geom_mat[side]
            row = self._wing_rows[side]
            pos[row] = root_p + root_r @ p_local
            mats[row] = root_r @ r_local

    def land(self) -> None:
        """Touch down: hand the body back to the walking physics at the flight position."""
        if not self.flying:
            return
        from flygym_demo.complex_terrain import LocomotionAction, apply_locomotion_action

        pos = self.position()
        yaw = self.heading_rad()
        self.flying = False
        d = self.data
        d.qpos[0:3] = [pos[0], pos[1], 1.0]
        d.qpos[3:7] = [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]
        d.qvel[:] = 0.0
        d.qpos[self._leg_adr] = self._leg_walk
        self.controller.reset(seed=self.seed)
        apply_locomotion_action(
            self.sim,
            FLY_NAME,
            LocomotionAction(
                joint_angles=self._leg_walk.copy(), adhesion_onoff=np.ones(6, dtype=bool)
            ),
        )
        self.sim.forward()
        self.sim.warmup(0.04)
        self._prev_xy = self.position()[:2].copy()

    # ----------------------------------------------------------------- sensors
    def obstacle_contacts(self) -> tuple[float, float, int]:
        """Contact force magnitude with obstacles on the left/right of the body axis."""
        if self.flying:
            left, right = self.flight.state.contact
            return left, right, int(left > 0) + int(right > 0)
        if len(self.obstacle_geoms) == 0 or self.data.ncon == 0:
            return 0.0, 0.0, 0
        ncon = self.data.ncon
        c = self.data.contact
        g1, g2 = c.geom1[:ncon], c.geom2[:ncon]
        hit = (np.isin(g1, self.obstacle_geoms) & self._fly_geom_mask[g2]) | (
            np.isin(g2, self.obstacle_geoms) & self._fly_geom_mask[g1]
        )
        if not hit.any():
            return 0.0, 0.0, 0
        thorax = self.position()
        h = self.heading_rad()
        left_axis = np.array([-math.sin(h), math.cos(h)])
        f = np.zeros(6)
        left = right = 0.0
        for k in np.nonzero(hit)[0]:
            mj.mj_contactForce(self.model, self.data, int(k), f)
            mag = float(np.linalg.norm(f[:3]))
            lateral = float(np.dot(c.pos[k][:2] - thorax[:2], left_axis))
            if lateral >= 0:
                left += mag
            else:
                right += mag
        return left, right, int(hit.sum())

    def luminance(self, refresh_s: float = 0.05) -> tuple[float, float]:
        if not self.vision:
            return (0.0, 0.0)
        if self._vision_age >= refresh_s:
            try:
                r = self.sim.get_ommatidia_readouts(FLY_NAME)  # (2 eyes, 721, 2 channels)
            except Exception as exc:  # no OpenGL context (e.g. GPU-less macOS VM, headless Linux)
                # Degrade explicitly: vision off, reason reported, the session keeps running.
                self.vision = False
                self.vision_error = f"{type(exc).__name__}: {exc}"
                self._luminance = (0.0, 0.0)
                return self._luminance
            self._luminance = (float(r[0].sum(axis=1).mean()), float(r[1].sum(axis=1).mean()))
            self._vision_age = 0.0
        return self._luminance

    def sensors(self) -> dict[str, float]:
        bp = self.sim.get_body_positions(FLY_NAME)
        out: dict[str, float] = {}
        for side, i in zip(("left", "right"), self._antennae, strict=True):
            od = odor_intensity(self.arena.odor_sources, bp[i][:2])
            out[f"odor_attractive_{side}"] = od["attractive"]
            out[f"odor_aversive_{side}"] = od["aversive"]
        lum = self.luminance()
        out["luminance_left"], out["luminance_right"] = lum
        cl, cr, n = self.obstacle_contacts()
        out["contact_left"] = 1.0 if cl > 1e-3 else 0.0
        out["contact_right"] = 1.0 if cr > 1e-3 else 0.0
        out["contact_force_left"], out["contact_force_right"] = cl, cr
        out["n_obstacle_contacts"] = float(n)
        xy = bp[self._thorax][:2]
        out["on_food"] = (
            1.0
            if bp[self._thorax][2] < 2.0  # standing; a fly passing over the patch does not feed
            and any(
                math.hypot(xy[0] - f.x_mm, xy[1] - f.y_mm) <= f.radius_mm for f in self.arena.food
            )
            else 0.0
        )
        out["airborne"] = 1.0 if self.flying else 0.0
        return out

    # -------------------------------------------------------------- geometry
    def mesh_pack(self) -> tuple[dict, bytes]:
        """Official NeuroMechFly meshes as compiled by MuJoCo (geom-local frame)."""
        m = self.model
        meta = {
            "geoms": [],
            "units": "mm",
            "source": "FlyGym 2.1.1 NeuroMechFly meshes "
            "(Apache-2.0), vertices as compiled by MuJoCo",
        }
        chunks: list[bytes] = []
        offset = 0
        for gi in self.mesh_geoms:
            mid = int(m.geom_dataid[gi])
            va, vn = int(m.mesh_vertadr[mid]), int(m.mesh_vertnum[mid])
            fa, fn = int(m.mesh_faceadr[mid]), int(m.mesh_facenum[mid])
            verts = np.ascontiguousarray(m.mesh_vert[va : va + vn], dtype=np.float32)
            faces = np.ascontiguousarray(m.mesh_face[fa : fa + fn], dtype=np.uint32)
            matid = int(m.geom_matid[gi])
            rgba = (m.mat_rgba[matid] if matid >= 0 else m.geom_rgba[gi]).tolist()
            meta["geoms"].append(
                {
                    "name": mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, int(gi)).split("/", 1)[-1],
                    "vertex_offset": offset,
                    "n_vertices": vn,
                    "face_offset": offset + verts.nbytes,
                    "n_faces": fn,
                    "rgba": [round(float(c), 4) for c in rgba],
                    "group": int(m.geom_group[gi]),
                }
            )
            chunks += [verts.tobytes(), faces.tobytes()]
            offset += verts.nbytes + faces.nbytes
        return meta, b"".join(chunks)

    def scene_objects(self) -> list[dict]:
        """Non-fly geometry (obstacles, lights, food, odour markers) for rendering."""
        m = self.model
        out = []
        for gi in range(m.ngeom):
            name = mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, gi) or ""
            if not name.startswith(("obstacle_", "light_", "food_", "odor_")):
                continue
            q = Rotation.from_matrix(self.data.geom_xmat[gi].reshape(3, 3)).as_quat(
                scalar_first=True
            )
            matid = int(m.geom_matid[gi])
            rgba = m.mat_rgba[matid] if matid >= 0 else m.geom_rgba[gi]
            out.append(
                {
                    "name": name,
                    "kind": name.split("_")[0],
                    "type": {
                        int(mj.mjtGeom.mjGEOM_BOX): "box",
                        int(mj.mjtGeom.mjGEOM_CYLINDER): "cylinder",
                        int(mj.mjtGeom.mjGEOM_SPHERE): "sphere",
                    }.get(int(m.geom_type[gi]), "other"),
                    "size": m.geom_size[gi].tolist(),
                    "pos": self.data.geom_xpos[gi].tolist(),
                    "quat": q.tolist(),
                    "rgba": [float(c) for c in rgba],
                }
            )
        return out
