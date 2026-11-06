import json

import pandas as pd

from flymind.experiments.compare import compare_experiments
from flymind.experiments.runner import run_experiment
from flymind.experiments.spec import ExpectedResult, ExperimentSpec
from flymind.experiments.templates import TEMPLATES, build_template


def test_every_template_builds_for_the_fixture(store):
    for key, (_t, _fn, datasets) in TEMPLATES.items():
        assert "synthetic_demo_v1" in datasets
        spec = build_template(key, "synthetic_demo_v1")
        assert spec.conditions and spec.dataset_id == "synthetic_demo_v1"
        ExperimentSpec.model_validate_json(spec.model_dump_json())  # round-trips


def test_run_persists_reproducible_records(store, tmp_path):
    spec = build_template("silencing", "synthetic_demo_v1")
    spec.n_trials = 3
    spec.expected = [
        ExpectedResult(
            readout="lhn_attr_l",
            condition="silenced",
            value_hz=0.0,
            tolerance_hz=0.5,
            source="silencing PN_attr_L removes all input to LHN_attr_L in the synthetic design",
        )
    ]
    d1 = run_experiment(spec, out_root=tmp_path, experiment_id="exp_a")
    d2 = run_experiment(spec, out_root=tmp_path, experiment_id="exp_b")
    rec = json.loads((d1 / "record.json").read_text())
    for key in ("dataset", "seeds", "runtime", "resolved_neurons", "summary", "assumptions"):
        assert key in rec
    assert rec["runtime"]["packages"]["flymind"]
    assert rec["expected_checks"][0]["status"] == "pass"
    s1 = pd.read_parquet(d1 / "spikes.parquet")
    s2 = pd.read_parquet(d2 / "spikes.parquet")
    pd.testing.assert_frame_equal(s1, s2)  # same spec + seed => identical results
    assert s1["root_id"].dtype == "int64"
    ro = pd.read_csv(d1 / "readouts.csv")
    intact = ro[(ro.condition == "intact") & (ro.readout == "lhn_attr_l")].mean_rate_hz.iloc[0]
    assert intact > 10
    cmp = compare_experiments(d1, d1, "intact", "silenced")
    delta = {r["readout"]: r["delta_hz"] for r in cmp["readouts"]}
    assert delta["lhn_attr_l"] < -10
    # replay from the saved spec gives the same readouts
    spec2 = ExperimentSpec.model_validate_json((d1 / "spec.json").read_text())
    d3 = run_experiment(spec2, out_root=tmp_path, experiment_id="exp_c")
    pd.testing.assert_frame_equal(ro, pd.read_csv(d3 / "readouts.csv"))
