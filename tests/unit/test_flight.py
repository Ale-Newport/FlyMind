"""Reduced-order flight model: aerodynamics, stability, manoeuvres, collisions (no MuJoCo)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from flymind.embodiment.arena import arena_preset
from flymind.embodiment.behavior import AutonomousPolicy, Observation, command_to_ds
from flymind.embodiment.flight import (
    MM,
    Box,
    FlightCommand,
    FlightSim,
    G,
    Morphology,
    bem_wrench,
    dickinson_cd,
    dickinson_cl,
    hover_trim,
    nominal_params,
    stroke_plane_tilt_for_hover,
    wrap_pi,
)


@pytest.fixture()
def sim() -> FlightSim:
    return FlightSim()


def run(sim: FlightSim, cmd: FlightCommand, seconds: float) -> None:
    for _ in range(int(round(seconds / 1e-3))):
        sim.step(cmd)


def test_dickinson_coefficients_match_the_published_fits():
    a = np.radians(np.array([0.0, 45.0, 90.0]))
    assert dickinson_cl(a)[1] == pytest.approx(1.80, abs=0.05)  # peak lift near 45 deg
    assert dickinson_cd(a)[0] == pytest.approx(0.37, abs=0.05)
    assert dickinson_cd(a)[2] > 3.0  # broadside drag is largest


def test_morphology_is_drosophila_sized():
    m = Morphology()
    assert 0.8e-6 < m.mass_kg < 1.3e-6  # ~1 mg
    assert m.wing_area_m2 == pytest.approx(2.0e-6, rel=0.1)  # ~2 mm^2 per wing
    assert 2.0e-3 < m.wing_length_m < 3.0e-3


def test_symmetric_wings_produce_no_side_force_roll_or_yaw():
    m = Morphology()
    f, mo = bem_wrench(
        m, nominal_params(m), stroke_plane_tilt_for_hover(), np.zeros(3), np.zeros(3)
    )
    ft, mt = f.sum(axis=0), mo.sum(axis=0)
    assert abs(ft[1]) < 1e-12
    assert abs(mt[0]) < 1e-15 and abs(mt[2]) < 1e-15


def test_thrust_grows_with_stroke_amplitude_and_lift_balances_weight_near_140_degrees():
    m = Morphology()
    beta = stroke_plane_tilt_for_hover()
    n_t = np.array([-math.sin(beta), 0.0, math.cos(beta)])
    thrust = [
        bem_wrench(m, nominal_params(m, a), beta, np.zeros(3), np.zeros(3))[0].sum(axis=0) @ n_t
        for a in np.radians([110, 130, 150, 170])
    ]
    assert all(b > a for a, b in zip(thrust, thrust[1:], strict=False))
    t140 = (
        bem_wrench(m, nominal_params(m, math.radians(140)), beta, np.zeros(3), np.zeros(3))[0].sum(
            axis=0
        )
        @ n_t
    )
    # D. melanogaster hovers with a stroke amplitude of roughly 140-150 deg (Fry et al. 2005)
    assert t140 == pytest.approx(m.weight_n, rel=0.1)


def test_wings_damp_rotation_and_translation():
    m = Morphology()
    beta = stroke_plane_tilt_for_hover()
    p = nominal_params(m)
    _, m0 = bem_wrench(m, p, beta, np.zeros(3), np.zeros(3))
    for axis in range(3):
        om = np.zeros(3)
        om[axis] = 20.0
        _, m1 = bem_wrench(m, p, beta, np.zeros(3), om)
        assert (m1.sum(axis=0) - m0.sum(axis=0))[axis] < 0  # flapping counter-torque
    f0, _ = bem_wrench(m, p, beta, np.zeros(3), np.zeros(3))
    f1, _ = bem_wrench(m, p, beta, np.array([0.3, 0.0, 0.0]), np.zeros(3))
    assert (f1.sum(axis=0) - f0.sum(axis=0))[0] < 0  # drag opposes motion


def test_wings_off_is_free_fall(sim):
    sim.reset(np.array([0, 0, 20e-3]))
    cmd = FlightCommand(wings=False)
    run(sim, cmd, 0.05)
    assert sim.state.v[2] == pytest.approx(-G * 0.05, rel=0.03)


def test_hover_is_stable_and_physiological():
    r = hover_trim(FlightSim(), 0.8)
    assert abs(r["z_mm"] - 6.0) < 0.3
    assert np.linalg.norm(r["v"]) < 0.01
    pitch = r["euler_deg"][1]
    assert 25 < pitch < 50  # body pitched nose-up in hover (Drosophila ~ 30-50 deg)
    amp = math.degrees(r["wing"][0])
    assert 120 < amp < 165


def test_takeoff_reaches_target_altitude(sim):
    sim.reset()
    cmd = FlightCommand(altitude=10e-3)
    run(sim, cmd, 1.5)
    assert sim.altitude() / MM == pytest.approx(10.0, abs=1.0)
    assert abs(sim.state.v[2]) < 0.01


def test_forward_flight_reaches_commanded_speed_with_bounded_attitude(sim):
    sim.reset(np.array([0, 0, 10e-3]))
    sim.state.engaged = True
    sim.state.wing = sim.p_nom.copy()
    run(sim, FlightCommand(altitude=10e-3, speed=0.15), 1.5)
    assert sim.state.v[0] == pytest.approx(0.15, rel=0.06)
    assert abs(sim.altitude() / MM - 10.0) < 1.0
    assert abs(sim.euler_deg()[2]) < 3  # no roll while flying straight


def test_saccade_turns_fast_without_diverging(sim):
    sim.reset(np.array([0, 0, 10e-3]))
    sim.state.engaged = True
    sim.state.wing = sim.p_nom.copy()
    run(sim, FlightCommand(altitude=10e-3, speed=0.15), 1.0)
    z0 = sim.altitude()
    target = wrap_pi(sim.heading() + math.pi / 2)
    run(sim, FlightCommand(altitude=10e-3, speed=0.15, heading=target), 0.15)
    assert abs(wrap_pi(sim.heading() - target)) < math.radians(8)  # a 90 deg saccade in <150 ms
    run(sim, FlightCommand(altitude=10e-3, speed=0.15, heading=target), 0.8)
    assert abs(wrap_pi(sim.heading() - target)) < math.radians(2)
    assert abs(sim.altitude() - z0) < 2e-3
    assert abs(sim.euler_deg()[2]) < 5  # banking recovers


def test_random_saccades_and_height_changes_never_lose_the_fly(sim):
    """Regression: a large heading change must not starve thrust (fly once fell to the floor)."""
    rng = np.random.default_rng(3)
    sim.reset(np.array([0, 0, 10e-3]))
    sim.state.engaged = True
    sim.state.wing = sim.p_nom.copy()
    sim.step(FlightCommand(altitude=10e-3))
    alt, target = 10e-3, 0.0
    zs, rolls = [], []
    for k in range(12000):
        if k % 900 == 0:
            target = wrap_pi(sim.heading() + float(np.clip(rng.normal(0, 1.0), -1.9, 1.9)))
            alt = float(np.clip(alt + rng.normal(0, 3e-3), 5.5e-3, 13e-3))
        sim.step(FlightCommand(altitude=alt, speed=0.16, heading=target))
        if k > 1500:
            zs.append(sim.altitude())
            rolls.append(abs(sim.euler_deg()[2]))
    assert min(zs) > 4.0e-3 and max(zs) < 16e-3
    assert max(rolls) < 15


def test_left_and_right_turns_are_mirror_images(sim):
    def path(turn: float):
        s = FlightSim()
        s.reset(np.array([0, 0, 10e-3]))
        s.state.engaged = True
        s.state.wing = s.p_nom.copy()
        run(s, FlightCommand(altitude=10e-3, speed=0.12, yaw_rate=turn), 1.0)
        return s.thorax_position()

    left, right = path(2.0), path(-2.0)
    assert left[1] > 5e-3
    assert right[1] == pytest.approx(-left[1], rel=0.02, abs=1e-4)
    assert right[0] == pytest.approx(left[0], rel=0.02, abs=1e-4)


def test_landing_is_gentle_and_stops_the_wings(sim):
    sim.reset(np.array([0, 0, 10e-3]))
    sim.state.engaged = True
    sim.state.wing = sim.p_nom.copy()
    stand = sim.m.stand_height_m
    cmd = FlightCommand(altitude=stand - 0.6e-3, descend_limit=0.05, speed=0.0)
    worst_vz = 0.0
    for _ in range(3000):
        sim.step(cmd)
        if sim.state.on_ground:
            break
        worst_vz = min(worst_vz, sim.state.v[2])
    assert sim.state.on_ground
    assert worst_vz > -0.12  # soft touch-down
    run(sim, FlightCommand(wings=False), 0.1)
    assert not sim.state.engaged
    assert sim.altitude() >= stand - 1e-9  # never through the floor


def test_obstacles_stop_the_fly(sim):
    sim.reset(np.array([0, 0, 1.5e-3]))
    sim.obstacles = [Box(x=12e-3, y=0.0, half_x=0.5e-3, half_y=10e-3, height=8e-3)]
    sim.state.engaged = True
    sim.state.wing = sim.p_nom.copy()
    run(sim, FlightCommand(altitude=4e-3, speed=0.2), 1.5)
    assert sim.thorax_position()[0] < 12e-3 - 0.5e-3  # stopped at the wall face
    assert sim.state.contact[0] + sim.state.contact[1] >= 0.0


def test_flight_is_deterministic(sim):
    def final():
        s = FlightSim()
        s.reset()
        run(s, FlightCommand(altitude=8e-3, speed=0.1, yaw_rate=0.5), 0.5)
        return s.thorax_position()

    assert np.array_equal(final(), final())


def test_command_to_ds_is_symmetric():
    d = command_to_ds(1.0, 0.5)
    assert d[1] > d[0]  # positive turn steers left: shorter left strides
    e = command_to_ds(1.0, -0.5)
    assert d[0] == pytest.approx(e[1]) and d[1] == pytest.approx(e[0])


def _obs(t, x=0.0, y=0.0, z=1.16, heading=0.0, airborne=False, **sensors):
    base = {
        "odor_attractive_left": 0.0,
        "odor_attractive_right": 0.0,
        "odor_aversive_left": 0.0,
        "odor_aversive_right": 0.0,
        "contact_left": 0.0,
        "contact_right": 0.0,
        "on_food": 0.0,
    }
    base.update(sensors)
    return Observation(t, x, y, z, heading, base, airborne)


def test_policy_feeds_when_on_food_and_then_leaves():
    p = AutonomousPolicy(arena_preset("food"), seed=1)
    labels = []
    t = 0.0
    while t < 12.0:
        it = p.step(_obs(t, on_food=1.0 if t < 7.5 else 0.0))
        labels.append(it.label)
        t += 0.05
    assert "feeding" in labels
    assert "leaving the food" in labels
    assert labels.index("feeding") < labels.index("leaving the food")


def test_policy_steers_toward_the_stronger_antenna_in_flight():
    p = AutonomousPolicy(arena_preset("food"), seed=2)
    it = None
    for k in range(40):
        it = p.step(
            _obs(
                k * 0.05,
                airborne=True,
                z=9.0,
                odor_attractive_left=0.35,
                odor_attractive_right=0.15,
            )
        )
    assert it is not None and it.locomotion == "fly"
    assert it.heading is not None and wrap_pi(it.heading) > 0  # steer left (left antenna stronger)


def test_policy_lands_when_odour_is_strong_in_flight():
    p = AutonomousPolicy(arena_preset("food"), seed=3)
    it = None
    for k in range(10):
        it = p.step(
            _obs(
                k * 0.05,
                airborne=True,
                z=9.0,
                odor_attractive_left=0.55,
                odor_attractive_right=0.55,
            )
        )
    assert it is not None and it.locomotion == "walk" and "landing" in it.label


def test_policy_is_reproducible_for_a_seed():
    def trace(seed):
        p = AutonomousPolicy(arena_preset("empty"), seed=seed)
        return [p.step(_obs(k * 0.05)).label for k in range(400)]

    assert trace(5) == trace(5)


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_policy_finds_and_feeds_on_the_food_patch_when_walking(seed):
    """Policy in the loop with an idealised unicycle walker and the analytic odour field."""
    from flymind.embodiment.arena import odor_intensity

    arena = arena_preset("food")
    pol = AutonomousPolicy(arena, seed)
    pol.p.walk_to_fly_hazard_hz = 0.0  # stay on foot
    x = y = h = 0.0
    food = arena.food[0]
    fed = False
    for k in range(30_000):  # 30 s
        t = k * 1e-3
        lat = np.array([-math.sin(h), math.cos(h)])
        fw = np.array([math.cos(h), math.sin(h)])
        pos = np.array([x, y])
        al = odor_intensity(arena.odor_sources, pos + 0.5 * fw + 0.35 * lat)["attractive"]
        ar = odor_intensity(arena.odor_sources, pos + 0.5 * fw - 0.35 * lat)["attractive"]
        on_food = 1.0 if math.hypot(x - food.x_mm, y - food.y_mm) <= food.radius_mm else 0.0
        it = pol.step(
            _obs(
                t, x, y, 1.16, h, odor_attractive_left=al, odor_attractive_right=ar, on_food=on_food
            )
        )
        if it.label == "feeding":
            fed = True
            break
        h = wrap_pi(h + 1.5 * it.turn * 1e-3)
        x += 8.0 * max(it.forward, 0) * math.cos(h) * 1e-3
        y += 8.0 * max(it.forward, 0) * math.sin(h) * 1e-3
    assert fed
