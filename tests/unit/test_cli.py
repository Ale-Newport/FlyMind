"""Command-line interface checks on the synthetic fixture."""

import json

from typer.testing import CliRunner


def test_data_info_json_lists_installed_datasets(store):
    from flymind.cli import app

    r = CliRunner().invoke(app, ["data", "info", "--json"])
    assert r.exit_code == 0, r.output
    rows = json.loads(r.output)
    assert [row["dataset_id"] for row in rows] == ["synthetic_demo_v1"]
    row = rows[0]
    assert row["synthetic"] is True and row["validation_status"] == "passed"
    assert row["n_neurons"] == store.n_neurons and "manifest" not in row


def test_data_info_json_for_one_dataset_includes_manifest(store):
    from flymind.cli import app

    r = CliRunner().invoke(app, ["data", "info", "synthetic_demo_v1", "--json"])
    assert r.exit_code == 0, r.output
    (row,) = json.loads(r.output)
    assert row["manifest"]["dataset_id"] == "synthetic_demo_v1"


def test_data_info_unknown_dataset_fails():
    from flymind.cli import app

    r = CliRunner().invoke(app, ["data", "info", "not_installed"])
    assert r.exit_code == 1
