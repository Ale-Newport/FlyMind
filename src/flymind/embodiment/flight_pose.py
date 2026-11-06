"""Flight posture and wing drawing for the NeuroMechFly mesh (rendering only, no physics).

FlyGym's body has rigid wings and no wing joints, so while the flight model
(:mod:`flymind.embodiment.flight`) integrates the body, the browser is sent poses obtained by

* writing the flight body pose into the MuJoCo root joint,
* blending the legs between the walking pose and a folded flight posture (``TUCK_POSE``),
* re-posing each wing mesh as a rigid rotation about its hinge, using the same wing frame that
  the aerodynamic model uses (``flight.wing_frame``), so what is drawn is what is simulated.

Wingbeats are drawn in slow motion (the real 200 Hz stroke would alias at the 30 Hz stream rate);
the phase is therefore supplied by the caller.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from flymind.embodiment.flight import ROTATION_VEL_FRACTION, wing_frame

# Joint (without the "fly/" prefix) -> angle (rad) of the flight posture: legs folded against
# the body with the hind legs trailing. Solved once by inverse kinematics on the NeuroMechFly v2
# model (tarsus tips in the thorax frame, mm: front (0.55, +-0.40, -0.62), middle
# (-0.50, +-0.62, -0.78), hind (-1.75, +-0.40, -0.78)); see docs/scientific/flight.md.
TUCK_POSE: dict[str, float] = {
    "c_thorax-lf_coxa-yaw": 0.0727,
    "c_thorax-lf_coxa-pitch": 0.3217,
    "c_thorax-lf_coxa-roll": 0.9563,
    "lf_coxa-lf_trochanterfemur-pitch": -3.1162,
    "lf_coxa-lf_trochanterfemur-roll": 0.7102,
    "lf_trochanterfemur-lf_tibia-pitch": 2.6123,
    "lf_tibia-lf_tarsus1-pitch": -0.849,
    "c_thorax-lm_coxa-yaw": 1.2266,
    "c_thorax-lm_coxa-pitch": -0.1269,
    "c_thorax-lm_coxa-roll": 1.762,
    "lm_coxa-lm_trochanterfemur-pitch": -1.9826,
    "lm_coxa-lm_trochanterfemur-roll": -0.118,
    "lm_trochanterfemur-lm_tibia-pitch": 3.3629,
    "lm_tibia-lm_tarsus1-pitch": -1.0074,
    "c_thorax-lh_coxa-yaw": 0.6987,
    "c_thorax-lh_coxa-pitch": 0.9807,
    "c_thorax-lh_coxa-roll": 2.3226,
    "lh_coxa-lh_trochanterfemur-pitch": -2.1053,
    "lh_coxa-lh_trochanterfemur-roll": -0.1224,
    "lh_trochanterfemur-lh_tibia-pitch": 2.5061,
    "lh_tibia-lh_tarsus1-pitch": 0.0638,
    "c_thorax-rf_coxa-yaw": 0.0727,
    "c_thorax-rf_coxa-pitch": 0.3217,
    "c_thorax-rf_coxa-roll": 0.9563,
    "rf_coxa-rf_trochanterfemur-pitch": -3.1163,
    "rf_coxa-rf_trochanterfemur-roll": 0.7102,
    "rf_trochanterfemur-rf_tibia-pitch": 2.6123,
    "rf_tibia-rf_tarsus1-pitch": -0.849,
    "c_thorax-rm_coxa-yaw": 1.2266,
    "c_thorax-rm_coxa-pitch": -0.1269,
    "c_thorax-rm_coxa-roll": 1.762,
    "rm_coxa-rm_trochanterfemur-pitch": -1.9826,
    "rm_coxa-rm_trochanterfemur-roll": -0.118,
    "rm_trochanterfemur-rm_tibia-pitch": 3.3629,
    "rm_tibia-rm_tarsus1-pitch": -1.0075,
    "c_thorax-rh_coxa-yaw": 0.6987,
    "c_thorax-rh_coxa-pitch": 0.9807,
    "c_thorax-rh_coxa-roll": 2.3226,
    "rh_coxa-rh_trochanterfemur-pitch": -2.1053,
    "rh_coxa-rh_trochanterfemur-roll": -0.1224,
    "rh_trochanterfemur-rh_tibia-pitch": 2.5061,
    "rh_tibia-rh_tarsus1-pitch": 0.0638,
}


def smoothstep(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def wing_rest_frame(verts_thorax: np.ndarray, sigma: float) -> np.ndarray:
    """Columns (span, chord, normal) of the folded wing mesh, from its principal axes.

    Span runs from the hinge to the tip (backwards at rest). The chord runs from the leading
    edge, which faces outward when the wing is folded over the abdomen, to the trailing edge.
    """
    c = verts_thorax.mean(axis=0)
    _, _, vt = np.linalg.svd(verts_thorax - c, full_matrices=False)
    span = vt[0] if vt[0][0] < 0 else -vt[0]
    chord = vt[1] - np.dot(vt[1], span) * span
    chord /= np.linalg.norm(chord)
    if np.dot(chord, sigma * np.array([0.0, 1.0, 0.0])) > 0:  # leading edge outward
        chord = -chord
    normal = np.cross(span, chord)
    return np.column_stack([span, chord, normal])


def wing_display_rotation(
    rest: np.ndarray, sigma: float, wing: np.ndarray, side: int, beta: float, phase: float
) -> np.ndarray:
    """Rotation taking the folded wing mesh to its flapping pose, blended with the folded pose
    while the stroke amplitude is still small (wings unfolding at take-off / folding at landing).
    """
    amp, centre, pitch = float(wing[side]), float(wing[2 + side]), float(wing[4 + side])
    phi = centre + 0.5 * amp * math.cos(phase)
    dphi = -0.5 * amp * math.sin(phase)
    dphi_ref = ROTATION_VEL_FRACTION * 0.5 * max(amp, 1e-3)
    s, c, n, _ = wing_frame(
        np.asarray(phi), np.asarray(dphi), np.asarray(pitch), sigma, beta, dphi_ref
    )
    flap = np.column_stack([s, c, n]) @ rest.T
    k = smoothstep((amp - 0.25) / 0.9)
    if k >= 1.0:
        return flap
    if k <= 0.0:
        return np.eye(3)
    sl = Slerp([0.0, 1.0], Rotation.from_matrix([np.eye(3), flap]))
    return sl(k).as_matrix()
