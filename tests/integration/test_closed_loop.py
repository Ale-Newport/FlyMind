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
    s = FlySession(FlySessionConfig(arena=arena_preset("light"), duration_s=0.2))
    s.run_blocking()
    out = s.save(tmp_path)
    import json

    rec = json.loads((out / "record.json").read_text())
    frames = np.load(out / "frames.npz")
    assert frames["poses"].shape[1] == len(s.body.mesh_geoms) and frames["poses"].shape[2] == 7
    assert rec["components"]["motor_controller"].startswith("FlyGym HybridTurningController")
    assert s.body.vision and math.isfinite(s.trajectory()["sensor_luminance_left"].iloc[-1])
