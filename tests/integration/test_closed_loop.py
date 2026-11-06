"""Integrated MuJoCo + brain tests (FlyGym physics; slower)."""

import math

import numpy as np
import pytest

from flymind.brain.session import NetworkConfig, SessionConfig, StimulusSpec
from flymind.connectome.selectors import NeuronSelector
from flymind.embodiment.arena import arena_preset
from flymind.embodiment.session import BaselineCommand, FlySession, FlySessionConfig

pytestmark = pytest.mark.physics


def test_baseline_walks_and_turns_left_for_positive_turn(store):
    s = FlySession(
        FlySessionConfig(
            arena=arena_preset("empty"),
            duration_s=0.6,
            baseline=BaselineCommand(forward=1.0, turn=0.5),
        )
    )
    s.run_blocking()
    m = s.metrics()
    assert m["distance_travelled_mm"] > 3
    assert m["heading_change_deg"] > 20  # +turn steers left (counter-clockwise)


def test_obstacle_contact_is_sensed(store):
    s = FlySession(FlySessionConfig(arena=arena_preset("obstacle"), duration_s=1.0))
    s.run_blocking()
    assert s.metrics()["collision_onsets"] >= 1


def test_zero_neural_output_means_no_walking(store):
    # no sensory drive in an empty arena: descending neurons are silent -> command is zero
    cfg = FlySessionConfig(
        arena=arena_preset("empty"),
        controller="neural",
        duration_s=0.3,
        brain=SessionConfig(dataset_id="synthetic_demo_v1", network=NetworkConfig(mode="demo")),
    )
    s = FlySession(cfg)
    s.run_blocking()
    assert s.metrics()["mean_abs_descending"] == 0.0
    assert s.metrics()["distance_travelled_mm"] < 1.0


def test_sensors_to_neurons_to_motor_and_back(store):
    cfg = FlySessionConfig(
        arena=arena_preset("food"),
        controller="neural",
        duration_s=0.6,
        brain=SessionConfig(dataset_id="synthetic_demo_v1", network=NetworkConfig(mode="demo")),
    )
    s = FlySession(cfg)
    s.run_blocking()
    df = s.trajectory()
    # world -> sensors: odour at the antennae is non-zero in the food arena
    assert (df["sensor_odor_attractive_left"] > 0).all()
    # sensors -> neural inputs: the encoder drove the mapped ORNs
    assert df["input_odor_attractive_left->orn_attr_l"].max() > 0
    # neural outputs -> motor: descending readout produced a non-zero command and movement
    assert df["rate_dn_fwd_l"].max() > 0 and np.abs(df[["ds_left", "ds_right"]]).max().max() > 0
    assert s.metrics()["distance_travelled_mm"] > 0.5
    # movement -> new sensor readings: the odour sampled at the antennae changes over time
    assert df["sensor_odor_attractive_left"].std() > 0
    # spikes were recorded by the brain session
    assert len(s.brain.spikes) > 0


def test_neural_perturbation_changes_motor_output(store):
    def run(interventions):
        cfg = FlySessionConfig(
            arena=arena_preset("empty"),
            controller="neural",
            duration_s=0.4,
            brain=SessionConfig(
                dataset_id="synthetic_demo_v1",
                network=NetworkConfig(mode="demo"),
                stimuli=[StimulusSpec(selector=NeuronSelector(group="lhn_attr_l"), rate_hz=150)],
                interventions=interventions,
            ),
        )
        s = FlySession(cfg)
        s.run_blocking()
        return s.trajectory()

    from flymind.brain.session import InterventionSpec

    intact = run([])
    assert intact["rate_dn_turn_l"].max() > 0
    turn_intact = (intact["ds_right"] - intact["ds_left"]).mean()
    for mode in ("block_output", "clamp"):
        # a silenced descending neuron no longer contributes to the motor command
        sil = run(
            [
                InterventionSpec(
                    kind="silence", mode=mode, selector=NeuronSelector(group="dn_turn_l")
                )
            ]
        )
        assert sil["rate_dn_turn_l"].max() == 0
        assert (sil["ds_right"] - sil["ds_left"]).mean() < turn_intact


def test_recording_save_and_replay_files(store, tmp_path):
    s = FlySession(FlySessionConfig(arena=arena_preset("empty"), duration_s=0.2))
    s.run_blocking()
    out = s.save(tmp_path)
    import json

    rec = json.loads((out / "record.json").read_text())
    frames = np.load(out / "frames.npz")
    assert frames["poses"].shape[1] == len(s.body.mesh_geoms) and frames["poses"].shape[2] == 7
    assert rec["components"]["motor_controller"].startswith("FlyGym HybridTurningController")
    assert (out / "trajectory.parquet").is_file() and (out / "joints.parquet").is_file()


def test_compound_eye_vision_reads_luminance(store, rendering):
    s = FlySession(FlySessionConfig(arena=arena_preset("light"), duration_s=0.2))
    s.run_blocking()
    lum = s.trajectory()["sensor_luminance_left"]
    assert s.body.vision and s.body.vision_error is None
    assert math.isfinite(lum.iloc[-1]) and lum.iloc[-1] > 0


def test_vision_degrades_explicitly_without_opengl(store, monkeypatch):
    s = FlySession(FlySessionConfig(arena=arena_preset("light"), duration_s=0.1))

    def no_gl(*_a, **_k):
        raise RuntimeError("invalid pixel format")

    monkeypatch.setattr(s.body.sim, "get_ommatidia_readouts", no_gl)
    s.run_blocking()  # keeps running instead of failing
    assert s.status == "finished" and not s.body.vision
    assert "invalid pixel format" in s.summary()["vision_error"]
    assert (s.trajectory()["sensor_luminance_left"] == 0).all()


# ------------------------------------------------------------------------------- flight
def test_flight_cycle_walk_takeoff_fly_land_walk(store):
    from flymind.embodiment.session import CommandStep

    s = FlySession(
        FlySessionConfig(
            arena=arena_preset("empty"),
            duration_s=2.6,
            baseline=BaselineCommand(
                forward=0.5,
                turn=0.0,
                schedule=[
                    CommandStep(t_s=0.1, forward=0.5, turn=0.0, locomotion="fly", altitude_mm=9),
                    CommandStep(t_s=1.4, forward=0.0, turn=0.0, locomotion="walk"),
                ],
            ),
        )
    )
    s.run_blocking()
    m = s.metrics()
    assert m["n_takeoffs"] == 1 and m["n_touchdowns"] == 1
    assert 4 < m["max_altitude_mm"] < 14
    assert m["airborne_time_s"] > 0.8
    assert s.loco.state == "ground" and not s.body.flying
    assert s.body.position()[2] < 2.0  # standing again on the walking physics
    kinds = [a["action"] for a in s.actions]
    assert kinds.index("takeoff") < kinds.index("landing") < kinds.index("touchdown")


def test_streamed_poses_flap_the_real_wing_meshes_during_flight(store):
    s = FlySession(FlySessionConfig(arena=arena_preset("empty"), duration_s=0.5, locomotion="fly"))
    s.run_blocking()
    b = s.body
    assert b.flying and b.flight.state.engaged
    a, c = b.geom_poses(wing_phase=0.0), b.geom_poses(wing_phase=math.pi)
    wings = b._wing_rows
    other = [i for i in range(len(a)) if i not in wings]
    assert not np.allclose(a[wings], c[wings], atol=1e-3)  # wings moved
    assert np.allclose(a[other], c[other], atol=1e-6)  # the rest of the body did not
    # airborne legs are folded: no mesh below the thorax by more than the body height
    assert (a[:, 2].min()) > 0.0


def test_flight_sensors_report_airborne_and_never_feed_in_the_air(store):
    s = FlySession(FlySessionConfig(arena=arena_preset("food"), duration_s=0.4, locomotion="fly"))
    s.run_blocking()
    sens = s.body.sensors()
    assert sens["airborne"] == 1.0 and sens["on_food"] == 0.0


def test_autonomous_policy_runs_end_to_end(store):
    cfg = FlySessionConfig(
        arena=arena_preset("food"), controller="autonomous", duration_s=1.0, record_hz=100
    )
    s = FlySession(cfg)
    s.run_blocking()
    df = s.trajectory()
    assert set(df["behavior"]) <= {
        "resting",
        "walking",
        "tracking odour on foot",
        "searching near the odour source",
        "returning to the arena",
        "taking off",
        "feeding",
        "leaving the food",
    }
    assert s.provenance()["evidence"] == "demonstration"
    assert "flight" in s.provenance()["components"]
