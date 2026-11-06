"""Reduced-order insect flight: wingbeat-averaged quasi-steady aerodynamics + 6-DoF rigid body.

FlyGym 2.x (NeuroMechFly v2) is a walking model: its wings are rigid meshes. Flight is
therefore a FlyMind component, kept deliberately small and fully documented:

* **Aerodynamics** - blade-element model of both wings. Each wing section produces
  translational lift and drag with the empirical coefficients measured on a dynamically
  scaled *Drosophila* wing (Dickinson, Lehmann & Sane 1999, Science 284:1954):
  ``C_L(a) = 0.225 + 1.58 sin(2.13 a - 7.2 deg)``, ``C_D(a) = 1.92 - 1.55 cos(2.04 a - 9.83 deg)``.
  Forces are averaged over one wingbeat, so the rigid body is integrated at 1 ms instead of
  resolving the 200 Hz stroke. The relative air velocity of every section includes the body
  velocity and rotation, which yields flapping-counter-torque damping and speed-dependent
  drag without extra terms.
* **Not modelled** (limitations, reported with every flight session): rotational circulation,
  added mass, wake capture, wing/body interference, ground effect, wind, within-stroke force
  oscillations (the body filters them), the haltere feedback loop.
* **Body** - mass, centre of mass, inertia, wing length, wing area, chord profile and hinge
  positions come from the NeuroMechFly v2 mesh model (see ``Morphology``).
* **Control** - a cascaded flight controller (velocity -> thrust vector -> attitude ->
  wing-kinematics allocation). Its job is the one the fly's nervous system performs; its
  implementation is engineering, *not* the connectome. Wing kinematics (stroke amplitude,
  stroke-centre offset, wing pitch of each wing) are the actuators, bounded to the ranges
  reported for *Drosophila* (stroke amplitude up to ~170 deg).

Frames: world ENU (x, y, z up), SI units inside this module; body frame x forward, y left,
z up with origin at the centre of mass. ``R`` rotates body to world.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

RHO_AIR = 1.2  # kg m^-3
G = 9.81  # m s^-2
MM = 1e-3


# --------------------------------------------------------------------------- morphology
@dataclass(frozen=True)
class Morphology:
    """Drosophila melanogaster as represented by the NeuroMechFly v2 model (FlyGym 2.1.1).

    Mass, inertia, centre of mass, wing length, area, chord profile and hinge positions were
    measured from the model's mesh/inertial data (``FlyBody.morphology_from_model`` redoes
    this measurement). Values in SI, body frame at the centre of mass.
    """

    mass_kg: float = 1.0243e-6
    inertia: np.ndarray = field(
        default_factory=lambda: np.array(
            [
                [1.5334e-13, -5.29e-16, -2.4725e-14],
                [-5.29e-16, 5.6750e-13, -6.5e-17],
                [-2.4725e-14, -6.5e-17, 5.7638e-13],
            ]
        )
    )
    wing_length_m: float = 2.404e-3
    #: chord (m) in 12 equal bins from root to tip
    chord_profile_m: np.ndarray = field(
        default_factory=lambda: (
            np.array(
                [0.256, 0.538, 0.787, 0.907, 0.993, 1.052, 1.054, 1.033, 0.989, 0.934, 0.829, 0.557]
            )
            * MM
        )
    )
    #: left wing hinge relative to the centre of mass (right wing mirrors y)
    hinge_left_m: np.ndarray = field(default_factory=lambda: np.array([0.187, 0.343, 0.222]) * MM)
    #: thorax (MuJoCo root body) origin relative to the centre of mass, body frame
    thorax_from_com_m: np.ndarray = field(
        default_factory=lambda: np.array([0.8168, -0.0005, 0.1258]) * MM
    )
    #: height of the thorax origin above the ground while standing on extended legs
    stand_height_m: float = 1.157e-3
    #: effective drag area (Cd*A) of the body along its x, y, z axes
    body_cda_m2: np.ndarray = field(default_factory=lambda: np.array([0.5, 2.4, 2.4]) * 1e-6)
    body_radius_m: float = 1.0e-3  # collision radius around the thorax origin

    @property
    def wing_area_m2(self) -> float:
        n = len(self.chord_profile_m)
        return float(self.chord_profile_m.sum() * self.wing_length_m / n)

    @property
    def weight_n(self) -> float:
        return self.mass_kg * G


# ------------------------------------------------------------------------- wing parameters
# p = [amp_L, amp_R, centre_L, centre_R, pitch_L, pitch_R]  (rad)
P_NAMES = ("amp_l", "amp_r", "centre_l", "centre_r", "pitch_l", "pitch_r")
P_MIN = np.array([0.9, 0.9, -0.55, -0.55, 0.30, 0.30])
P_MAX = np.array([3.0, 3.0, 0.55, 0.55, 1.25, 1.25])
WINGBEAT_HZ = 200.0
N_PHASE = 16
N_SPAN = 6
# smooth supination/pronation: fraction of peak stroke velocity at which the wing has
# rotated halfway (Drosophila rotates through ~20 % of the stroke)
ROTATION_VEL_FRACTION = 0.25


def dickinson_cl(alpha: np.ndarray) -> np.ndarray:
    a = np.degrees(alpha)
    return 0.225 + 1.58 * np.sin(np.radians(2.13 * a - 7.2))


def dickinson_cd(alpha: np.ndarray) -> np.ndarray:
    a = np.degrees(alpha)
    return 1.92 - 1.55 * np.cos(np.radians(2.04 * a - 9.83))


def stroke_basis(beta: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Stroke-plane axes in the body frame (``beta`` > 0 tilts the front of the plane up)."""
    ex = np.array([math.cos(beta), 0.0, math.sin(beta)])
    ey = np.array([0.0, 1.0, 0.0])
    ez = np.array([-math.sin(beta), 0.0, math.cos(beta)])
    return ex, ey, ez


def wing_frame(
    phi: np.ndarray, dphi: np.ndarray, pitch: np.ndarray, sigma: float, beta: float, dphi_ref: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Span ``s``, chord ``c`` (leading -> trailing edge), normal ``n`` and tangent ``t`` axes.

    ``phi`` is the stroke angle (positive = forward), ``pitch`` the geometric angle of attack at
    mid-stroke. The chord rotates smoothly through the stroke reversal.
    """
    ex, ey, ez = stroke_basis(beta)
    cphi, sphi = np.cos(phi)[..., None], np.sin(phi)[..., None]
    s = cphi * sigma * ey + sphi * ex
    t = -sphi * sigma * ey + cphi * ex
    gamma = 0.5 * math.pi - (0.5 * math.pi - pitch) * np.tanh(dphi / dphi_ref)
    c = -np.cos(gamma)[..., None] * t - np.sin(gamma)[..., None] * ez
    n = np.cross(s, c)
    return s, c, n, t


def wing_stroke(amp: np.ndarray, centre: np.ndarray, theta: np.ndarray):
    """Sinusoidal stroke: angle and angular velocity (per unit wingbeat angular frequency)."""
    phi = centre[..., None] + 0.5 * amp[..., None] * np.cos(theta)
    dphi = -0.5 * amp[..., None] * np.sin(theta)
    return phi, dphi


def _cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cross product on the last axis (np.cross has a large per-call overhead)."""
    return np.stack(
        [
            a[..., 1] * b[..., 2] - a[..., 2] * b[..., 1],
            a[..., 2] * b[..., 0] - a[..., 0] * b[..., 2],
            a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0],
        ],
        axis=-1,
    )


_SIGMA = np.array([1.0, -1.0])
_THETA = (np.arange(N_PHASE) + 0.5) * (2 * math.pi / N_PHASE)
_XI = (np.arange(N_SPAN) + 0.5) / N_SPAN


def bem_wrench(
    morph: Morphology,
    p: np.ndarray,
    beta: float,
    v_body: np.ndarray,
    omega_body: np.ndarray,
    freq_hz: float = WINGBEAT_HZ,
) -> tuple[np.ndarray, np.ndarray]:
    """Wingbeat-averaged force and moment on the body from both wings.

    ``p`` has shape (..., 6) (batched over leading axes); returns (force, moment) with shape
    (..., 2, 3): per wing (left, right), body frame, about the centre of mass.
    """
    p = np.asarray(p, dtype=float)
    lead = p.shape[:-1]
    pf = p.reshape(-1, 6)
    nb = pf.shape[0]
    amp, centre, pitch = pf[:, 0:2], pf[:, 2:4], pf[:, 4:6]  # (B, 2)
    w_wb = 2 * math.pi * freq_hz
    phi, dphi = wing_stroke(amp, centre, _THETA)  # (B, 2, Np)
    n_prof = len(morph.chord_profile_m)
    prof_x = (np.arange(n_prof) + 0.5) / n_prof
    chord = np.interp(_XI, prof_x, morph.chord_profile_m)
    r = _XI * morph.wing_length_m
    dr = morph.wing_length_m / N_SPAN
    dphi_ref = (ROTATION_VEL_FRACTION * 0.5 * np.maximum(amp, 1e-3))[..., None]  # (B, 2, 1)

    ex, ey, ez = stroke_basis(beta)
    sig = _SIGMA[None, :, None, None]  # (1, 2, 1, 1)
    cphi, sphi = np.cos(phi)[..., None], np.sin(phi)[..., None]  # (B, 2, Np, 1)
    s = cphi * sig * ey + sphi * ex  # span axis (B, 2, Np, 3)
    t = -sphi * sig * ey + cphi * ex  # tangent
    gamma = 0.5 * math.pi - (0.5 * math.pi - pitch[..., None]) * np.tanh(dphi / dphi_ref)
    c = -np.cos(gamma)[..., None] * t - np.sin(gamma)[..., None] * ez  # chord
    n = _cross(s, c)  # plate normal
    hinge = morph.hinge_left_m[None, :] * np.stack([np.ones(2), _SIGMA, np.ones(2)], axis=1)
    # (2, 3) -> (1, 2, 1, 1, 3)
    pos = hinge[None, :, None, None, :] + r[None, None, None, :, None] * s[:, :, :, None, :]
    v_stroke = (w_wb * dphi)[..., None, None] * r[None, None, None, :, None] * t[:, :, :, None, :]
    vb = np.broadcast_to(np.asarray(v_body, dtype=float), (nb, 3))[:, None, None, None, :]
    om = np.broadcast_to(np.asarray(omega_body, dtype=float), (nb, 3))[:, None, None, None, :]
    u_air = -(v_stroke + vb + _cross(om, pos))  # air velocity relative to each section
    s_b, n_b = s[:, :, :, None, :], n[:, :, :, None, :]
    u_perp = u_air - np.sum(u_air * s_b, axis=-1, keepdims=True) * s_b
    speed = np.sqrt(np.sum(u_perp * u_perp, axis=-1))
    dhat = u_perp / np.maximum(speed, 1e-9)[..., None]
    dn = np.sum(dhat * n_b, axis=-1)
    alpha = np.arcsin(np.minimum(np.abs(dn), 1.0))
    fn = np.where(dn >= 0, 1.0, -1.0)[..., None] * n_b
    lhat = fn - np.sum(fn * dhat, axis=-1, keepdims=True) * dhat
    lhat = lhat / np.maximum(np.sqrt(np.sum(lhat * lhat, axis=-1, keepdims=True)), 1e-9)
    q = 0.5 * RHO_AIR * speed**2 * chord * dr  # (B, 2, Np, Ns)
    df = (q * dickinson_cl(alpha))[..., None] * lhat + (q * dickinson_cd(alpha))[..., None] * dhat
    forces = df.sum(axis=3).mean(axis=2)  # (B, 2, 3)
    moments = _cross(pos, df).sum(axis=3).mean(axis=2)
    return forces.reshape(*lead, 2, 3), moments.reshape(*lead, 2, 3)


def stroke_plane_tilt_for_hover() -> float:
    """Nominal stroke-plane tilt relative to the body (front down = body pitched up in hover)."""
    return math.radians(-38.0)


def nominal_params(morph: Morphology | None = None, amp: float = 2.45) -> np.ndarray:
    return np.array([amp, amp, 0.0, 0.0, math.radians(45), math.radians(45)])


# -------------------------------------------------------------------------------- state
def rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def rot_y(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1.0, 0], [-s, 0, c]])


def rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0, 0], [0, c, -s], [0, s, c]])


def cross3(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.array(
        [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    )


def mat_to_quat(R: np.ndarray) -> np.ndarray:
    """Rotation matrix -> unit quaternion (w, x, y, z)."""
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = [0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        q = [(R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s]
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        q = [(R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s]
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        q = [(R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s]
    return np.array(q)


def skew(v: np.ndarray) -> np.ndarray:
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])


def vee(m: np.ndarray) -> np.ndarray:
    return np.array([m[2, 1], m[0, 2], m[1, 0]])


def exp_so3(w: np.ndarray) -> np.ndarray:
    th = float(np.linalg.norm(w))
    if th < 1e-12:
        return np.eye(3) + skew(w)
    k = skew(w / th)
    return np.eye(3) + math.sin(th) * k + (1 - math.cos(th)) * (k @ k)


def euler_zyx(R: np.ndarray) -> tuple[float, float, float]:
    """(yaw, pitch, roll); pitch > 0 is nose up."""
    yaw = math.atan2(R[1, 0], R[0, 0])
    pitch = math.asin(float(np.clip(R[2, 0], -1, 1)))  # R[2,0] = sin(nose-up angle)
    roll = math.atan2(R[2, 1], R[2, 2])
    return yaw, pitch, roll


def wrap_pi(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


@dataclass
class Box:
    """Axis-aligned-in-its-own-frame obstacle (metres, world frame)."""

    x: float
    y: float
    half_x: float
    half_y: float
    height: float
    yaw: float = 0.0


@dataclass
class FlightCommand:
    """High-level flight command (what the nervous system would specify)."""

    speed: float = 0.0  # m/s along the body heading
    lateral: float = 0.0  # m/s to the left
    yaw_rate: float = 0.0  # rad/s (integrated into the heading target)
    heading: float | None = None  # absolute heading target (rad); overrides yaw_rate
    altitude: float = 8e-3  # thorax height above ground (m)
    climb_limit: float = 0.20  # m/s
    descend_limit: float = 0.25  # m/s
    wings: bool = True  # False: wings off (landing complete / not flying)


@dataclass
class FlightState:
    p_com: np.ndarray
    v: np.ndarray
    R: np.ndarray
    omega: np.ndarray  # body frame
    wing: np.ndarray  # actual wing parameters (6)
    beta: float
    engaged: bool = False
    on_ground: bool = True
    t: float = 0.0
    phase: float = 0.0  # wingbeat phase for display (rad)
    contact: tuple[float, float] = (0.0, 0.0)
    wrench: np.ndarray = field(default_factory=lambda: np.zeros(6))


class FlightSim:
    """Free-flying rigid body with wing-kinematics actuators and a cascaded flight controller."""

    # controller gains
    TAU_VEL = 0.14  # s, horizontal velocity loop time constant
    TAU_VEL_Z = 0.06  # s, vertical (weight support reacts faster than lateral drift)
    A_MAX_H = 28.0  # m/s^2, horizontal acceleration limit
    A_MAX_UP = 14.0
    A_MAX_DN = 9.0
    K_ALT = 10.0  # 1/s, altitude loop
    KI_VEL = 22.0  # 1/s^2, horizontal velocity-loop integral gain
    KI_VEL_Z = 5.0  # 1/s^2, vertical (gentler: gravity is compensated feed-forward)
    ALPHA_MAX = np.array([9000.0, 6000.0, 5000.0])  # rad/s^2, attitude-loop demand limits
    THRUST_PRIORITY = 4.0  # weight of the thrust residual relative to the moments
    WN_ATT = 140.0  # rad/s, tilt loop natural frequency
    WN_YAW = 70.0  # rad/s, heading loop natural frequency
    ALPHA_YAW = 3500.0  # rad/s^2, limit on the heading acceleration demand
    ZETA_ATT = 1.1
    TAU_WING = 0.005  # s, wing-kinematics actuator lag (steering muscles ~1 wingbeat)
    TILT_MAX = math.radians(40.0)

    def __init__(self, morph: Morphology | None = None, freq_hz: float = WINGBEAT_HZ):
        self.m = morph or Morphology()
        self.freq_hz = freq_hz
        self.beta_hover = stroke_plane_tilt_for_hover()
        self.p_nom = nominal_params(self.m)
        self._inv_inertia = np.linalg.inv(self.m.inertia)
        self.obstacles: list[Box] = []
        self._jac: np.ndarray | None = None
        self._jac_age = 99
        self.reset()

    # ------------------------------------------------------------------- lifecycle
    def reset(
        self,
        thorax_xyz_m: np.ndarray | None = None,
        yaw: float = 0.0,
        velocity: np.ndarray | None = None,
    ) -> None:
        thorax = (
            np.array([0.0, 0.0, self.m.stand_height_m])
            if thorax_xyz_m is None
            else np.asarray(thorax_xyz_m, dtype=float)
        )
        R = rot_z(yaw)
        self.state = FlightState(
            p_com=thorax - R @ self.m.thorax_from_com_m,
            v=np.zeros(3) if velocity is None else np.asarray(velocity, dtype=float),
            R=R,
            omega=np.zeros(3),
            wing=np.array([0.0, 0.0, 0.0, 0.0, 0.5, 0.5]),
            beta=0.0,
        )
        self.psi_des = yaw
        self._a_int = np.zeros(3)
        self._p_cmd = self.p_nom.copy()
        self._w_wing = np.zeros(6)
        self._jac = None
        self._jac_age = 99
        self.last_cmd = FlightCommand()
        self.diag: dict[str, float] = {}

    # --------------------------------------------------------------- geometry helpers
    def thorax_position(self) -> np.ndarray:
        s = self.state
        return s.p_com + s.R @ self.m.thorax_from_com_m

    def heading(self) -> float:
        return euler_zyx(self.state.R)[0]

    def altitude(self) -> float:
        return float(self.thorax_position()[2])

    def airborne(self) -> bool:
        return self.altitude() > self.m.stand_height_m + 3e-4

    # ----------------------------------------------------------------------- control
    def _desired_beta(self, z: float) -> float:
        """Stroke plane stays body-level near the ground (take-off, landing) and tilts in air."""
        h = self.m.stand_height_m
        k = float(np.clip((z - h - 0.8e-3) / 2.0e-3, 0.0, 1.0))
        k = k * k * (3 - 2 * k)
        return self.beta_hover * k

    def _desired_attitude(self, f_des: np.ndarray, beta: float) -> np.ndarray:
        n_t = np.array([-math.sin(beta), 0.0, math.cos(beta)])
        b3 = f_des / max(float(np.linalg.norm(f_des)), 1e-12)
        # limit tilt from vertical
        tilt = math.acos(float(np.clip(b3[2], -1, 1)))
        if tilt > self.TILT_MAX:
            horiz = b3[:2] / max(float(np.linalg.norm(b3[:2])), 1e-9)
            b3 = np.array(
                [
                    math.sin(self.TILT_MAX) * horiz[0],
                    math.sin(self.TILT_MAX) * horiz[1],
                    math.cos(self.TILT_MAX),
                ]
            )
        base = rot_z(self.psi_des) @ rot_y(beta)  # thrust axis vertical, heading psi
        axis = np.array([-b3[1], b3[0], 0.0])  # z x b3
        sin_a = float(np.linalg.norm(axis))
        cos_a = float(b3[2])
        if sin_a < 1e-9:
            q = np.eye(3)
        else:
            q = exp_so3(axis / sin_a * math.atan2(sin_a, cos_a))
        del n_t
        return q @ base

    def _attitude_loop(self, r_des: np.ndarray, n_t: np.ndarray, st: FlightState) -> np.ndarray:
        """Tilt-prioritised attitude control: the thrust direction is corrected first and fast;
        the rotation about the thrust axis (heading) has its own gain and acceleration limit, so a
        large heading change cannot starve the tilt/thrust authority."""
        zeta = self.ZETA_ATT
        tgt = st.R.T @ (r_des @ n_t)  # desired thrust axis in the body frame
        axis = cross3(n_t, tgt)
        sin_a = float(np.linalg.norm(axis))
        angle = math.atan2(sin_a, float(n_t @ tgt))
        e_tilt = axis / sin_a * angle if sin_a > 1e-9 else np.zeros(3)
        r_red = st.R @ exp_so3(e_tilt)
        r_err = r_red.T @ r_des
        psi_e = math.atan2(
            float(vee(0.5 * (r_err - r_err.T)) @ n_t), 0.5 * (float(np.trace(r_err)) - 1.0)
        )
        w_n = float(st.omega @ n_t)
        a_tilt = self.WN_ATT**2 * e_tilt - 2 * zeta * self.WN_ATT * (st.omega - w_n * n_t)
        a_tilt = np.clip(a_tilt, -self.ALPHA_MAX, self.ALPHA_MAX)
        a_yaw = float(
            np.clip(
                self.WN_YAW**2 * psi_e - 2 * zeta * self.WN_YAW * w_n,
                -self.ALPHA_YAW,
                self.ALPHA_YAW,
            )
        )
        return a_tilt + a_yaw * n_t

    def _allocate(self, target: np.ndarray, n_t: np.ndarray, st: FlightState) -> np.ndarray:
        """Wing parameters producing [thrust along n_t, Mx, My, Mz] (damped least squares).

        One Gauss-Newton step from the *actual* wing state using the wrench measured in the
        previous physics step; the sensitivity matrix is refreshed every few steps.
        """
        w = self.m.weight_n
        scales = np.array([w, w * MM, w * MM, w * MM])
        p0 = st.wing
        if self._jac is None or self._jac_age >= 5:
            v_b = st.R.T @ st.v
            eps = 0.03
            batch = np.vstack([p0, p0 + eps * np.eye(6)])
            f, mo = bem_wrench(self.m, batch, st.beta, v_b, st.omega, self.freq_hz)
            ft, mt = f.sum(axis=-2), mo.sum(axis=-2)
            wr = np.concatenate([(ft @ n_t)[..., None], mt], axis=-1)
            self._jac = ((wr[1:] - wr[0]) / eps).T / scales[:, None]  # (4, 6) normalised
            self._jac_age = 0
        self._jac_age += 1
        f_w, m_w = self._w_wing[:3], self._w_wing[3:]
        current = np.concatenate([[f_w @ n_t], m_w])
        wts = np.array([self.THRUST_PRIORITY, 1.0, 1.0, 1.0])
        res = (target - current) / scales * wts
        jac = self._jac * wts[:, None]
        reg = np.diag([1.0, 1.0, 2.0, 2.0, 2.0, 2.0]) * 4e-3
        a = jac.T @ jac + reg
        b = jac.T @ res - reg @ (p0 - self.p_nom) * 0.15
        dp = np.linalg.solve(a, b)
        return np.clip(p0 + dp, P_MIN, P_MAX)

    # ------------------------------------------------------------------------- step
    def step(self, cmd: FlightCommand, dt: float = 1e-3) -> None:
        st = self.state
        m = self.m
        self.last_cmd = cmd
        if cmd.wings:
            st.engaged = True
        z = float(self.thorax_position()[2])
        yaw = self.heading()

        # heading target
        if cmd.heading is not None:
            self.psi_des = cmd.heading
        else:
            self.psi_des = wrap_pi(self.psi_des + cmd.yaw_rate * dt)
        # keep the target within reach of the actual heading (no wind-up)
        err_psi = wrap_pi(self.psi_des - yaw)
        if abs(err_psi) > 0.9:
            self.psi_des = wrap_pi(yaw + math.copysign(0.9, err_psi))

        if st.engaged and cmd.wings:
            # --- velocity loop in the heading frame
            hx = np.array([math.cos(yaw), math.sin(yaw), 0.0])
            hy = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
            vz_des = float(
                np.clip(self.K_ALT * (cmd.altitude - z), -cmd.descend_limit, cmd.climb_limit)
            )
            v_des = cmd.speed * hx + cmd.lateral * hy + vz_des * np.array([0, 0, 1.0])
            a_des = (v_des - st.v) / np.array([self.TAU_VEL, self.TAU_VEL, self.TAU_VEL_Z])
            ki = np.array([self.KI_VEL, self.KI_VEL, self.KI_VEL_Z])
            self._a_int = np.clip(
                self._a_int + ki * (v_des - st.v) * dt, [-4.0, -4.0, -1.5], [4.0, 4.0, 1.5]
            )
            a_des = a_des + self._a_int
            ah = float(np.linalg.norm(a_des[:2]))
            if ah > self.A_MAX_H:
                a_des[:2] *= self.A_MAX_H / ah
            a_des[2] = float(np.clip(a_des[2], -self.A_MAX_DN, self.A_MAX_UP))
            f_des = m.mass_kg * (a_des + np.array([0, 0, G]))
            st.beta += (self._desired_beta(z) - st.beta) * min(1.0, dt / 0.02)
            n_t = np.array([-math.sin(st.beta), 0.0, math.cos(st.beta)])
            r_des = self._desired_attitude(f_des, st.beta)
            alpha_des = self._attitude_loop(r_des, n_t, st)
            moment = m.inertia @ alpha_des + cross3(st.omega, m.inertia @ st.omega)
            thrust = float(f_des @ (st.R @ n_t))
            thrust = max(thrust, 0.15 * m.weight_n)
            target = np.array([thrust, moment[0], moment[1], moment[2]])
            self._p_cmd = self._allocate(target, n_t, st)
        else:
            # wings winding down (landing complete) or not started
            self._p_cmd = np.array([0.0, 0.0, 0.0, 0.0, 0.5, 0.5])
            st.beta += (0.0 - st.beta) * min(1.0, dt / 0.02)
            if not cmd.wings and float(st.wing[0] + st.wing[1]) < 0.05:
                st.engaged = False

        # --- wing actuator lag
        st.wing += (self._p_cmd - st.wing) * (1 - math.exp(-dt / self.TAU_WING))

        # --- aerodynamics and body
        v_b = st.R.T @ st.v
        if st.wing[0] > 0.02 or st.wing[1] > 0.02:
            f_w, m_w = bem_wrench(m, st.wing, st.beta, v_b, st.omega, self.freq_hz)
            f_body = f_w.sum(axis=0)
            m_body = m_w.sum(axis=0)
        else:
            f_body = np.zeros(3)
            m_body = np.zeros(3)
        self._w_wing = np.concatenate([f_body, m_body])
        f_body += -0.5 * RHO_AIR * m.body_cda_m2 * np.abs(v_b) * v_b
        st.wrench = np.concatenate([f_body, m_body])
        f_world = st.R @ f_body + np.array([0, 0, -m.weight_n])
        a = f_world / m.mass_kg
        om_dot = self._inv_inertia @ (m_body - cross3(st.omega, m.inertia @ st.omega))
        st.v = st.v + a * dt
        st.omega = st.omega + om_dot * dt
        st.p_com = st.p_com + st.v * dt
        st.R = st.R @ exp_so3(st.omega * dt)
        # re-orthonormalise (drift)
        u, _, vt = np.linalg.svd(st.R)
        st.R = u @ vt
        st.t += dt
        st.phase = (st.phase + 2 * math.pi * self.freq_hz * dt) % (2 * math.pi)
        self._collide()
        self.diag = {
            "thrust_over_weight": float(
                f_body @ np.array([-math.sin(st.beta), 0, math.cos(st.beta)])
            )
            / m.weight_n,
        }

    # ------------------------------------------------------------------- collisions
    def _collide(self) -> None:
        st = self.state
        m = self.m
        thorax = self.thorax_position()
        # ground: thorax origin cannot go below standing height
        if thorax[2] < m.stand_height_m:
            st.p_com[2] += m.stand_height_m - thorax[2]
            if st.v[2] < 0:
                st.v[2] = 0.0
            # ground friction on the planar velocity and rotation while standing
            speed = float(np.linalg.norm(st.v[:2]))
            if speed > 0:
                st.v[:2] *= max(0.0, 1 - 0.08 * 1.0)
            # settle roll/pitch to level on the ground (legs support the body)
            yaw, pitch, roll = euler_zyx(st.R)
            st.R = rot_z(yaw) @ rot_y(-pitch * 0.85) @ rot_x(roll * 0.85)
            st.omega *= 0.5
            self._a_int[2] = 0.0
            st.on_ground = True
        else:
            st.on_ground = thorax[2] <= m.stand_height_m + 1e-5
        left = right = 0.0
        yaw = self.heading()
        axis_left = np.array([-math.sin(yaw), math.cos(yaw)])
        for ob in self.obstacles:
            c, s = math.cos(ob.yaw), math.sin(ob.yaw)
            d = thorax[:2] - np.array([ob.x, ob.y])
            loc = np.array([c * d[0] + s * d[1], -s * d[0] + c * d[1]])
            half = np.array([ob.half_x, ob.half_y])
            zc = min(max(thorax[2], 0.0), ob.height)
            closest = np.clip(loc, -half, half)
            inside = bool(np.all(np.abs(loc) < half)) and thorax[2] < ob.height
            diff = loc - closest
            dz = thorax[2] - zc
            dist = math.sqrt(float(diff @ diff) + dz * dz)
            if inside:
                # push out along the axis of least penetration (horizontal)
                pen = half - np.abs(loc)
                k = int(np.argmin(pen))
                nloc = np.zeros(2)
                nloc[k] = math.copysign(1.0, loc[k] if loc[k] != 0 else 1.0)
                depth = pen[k] + m.body_radius_m
                nrm = np.array([c * nloc[0] - s * nloc[1], s * nloc[0] + c * nloc[1], 0.0])
            elif dist < m.body_radius_m:
                nloc = np.array([diff[0], diff[1]])
                n3 = np.array([nloc[0], nloc[1], dz])
                n3 = n3 / max(float(np.linalg.norm(n3)), 1e-12)
                nrm = np.array([c * n3[0] - s * n3[1], s * n3[0] + c * n3[1], n3[2]])
                depth = m.body_radius_m - dist
            else:
                continue
            st.p_com += nrm * depth
            vn = float(st.v @ nrm)
            if vn < 0:
                st.v -= (1 + 0.15) * vn * nrm
                force = abs(vn) * m.mass_kg / 1e-3
                lateral = float(np.dot(nrm[:2], axis_left))
                # obstacle on the side opposite to its outward normal
                if lateral <= 0:
                    left += force
                else:
                    right += force
        st.contact = (left, right)

    # ----------------------------------------------------------------- introspection
    def euler_deg(self) -> tuple[float, float, float]:
        yaw, pitch, roll = euler_zyx(self.state.R)
        return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


def hover_trim(sim: FlightSim, seconds: float = 0.6) -> dict:
    """Run hover for ``seconds`` and report the settled wing kinematics (used by tests)."""
    sim.reset(np.array([0, 0, 6e-3]))
    sim.state.engaged = True
    sim.state.wing = sim.p_nom.copy()
    cmd = FlightCommand(altitude=6e-3)
    for _ in range(int(seconds / 1e-3)):
        sim.step(cmd)
    return {
        "wing": sim.state.wing.copy(),
        "euler_deg": sim.euler_deg(),
        "z_mm": sim.altitude() / MM,
        "v": sim.state.v.copy(),
    }
