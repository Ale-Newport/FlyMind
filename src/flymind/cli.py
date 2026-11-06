"""FlyMind command-line interface (``uv run flymind --help``)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

app = typer.Typer(
    help="FlyMind: connectome simulation, virtual fly and 3D brain explorer.", no_args_is_help=True
)
data = typer.Typer(
    help="Install, import, validate and inspect connectome datasets.", no_args_is_help=True
)
sim = typer.Typer(help="Run brain simulations from the command line.", no_args_is_help=True)
fly = typer.Typer(help="Run the virtual fly headless.", no_args_is_help=True)
exp = typer.Typer(help="Run and inspect reproducible experiments.", no_args_is_help=True)
app.add_typer(data, name="data")
app.add_typer(sim, name="sim")
app.add_typer(fly, name="fly")
app.add_typer(exp, name="experiment")

BUNDLE_ALIASES = {
    "flywire-783": "flywire-783-open",
    "flywire-630": "flywire-630-shiu",
    "skeletons": "flywire-783-skeletons",
}


def _echo(msg: str) -> None:
    typer.echo(msg, err=True)


# ----------------------------------------------------------------------- data
@data.command("sources")
def data_sources():
    """List supported datasets, open sources and how to obtain restricted ones."""
    from flymind.connectome.adapters import ADAPTERS
    from flymind.connectome.sources import BUNDLES, FLYWIRE_LICENSE_NOTE

    typer.echo("Open bundles (fetched automatically, checksummed):")
    for alias, key in BUNDLES.items():
        b = BUNDLES[alias]
        cmd = next((a for a, k in BUNDLE_ALIASES.items() if k == key), key)
        size = sum(f.size_bytes or 0 for f in b.files) / 1e6
        typer.echo(f"  {cmd:<14} {b.title}  (~{size:,.0f} MB)\n      {b.description}")
    typer.echo("\nDataset adapters:")
    for a in ADAPTERS:
        typer.echo(f"  [{a.info.status:<9}] {a.info.dataset_id:<24} {a.info.title}")
    typer.echo(
        "\nFlyWire Codex files (sign-in required; never fetched by FlyMind):\n"
        "  1. Sign in at https://codex.flywire.ai/api/download and accept the terms.\n"
        "  2. Download e.g. neurons, classification, consolidated_cell_types, connections,\n"
        "     coordinates and names for version 783 into one folder.\n"
        "  3. uv run flymind data import <folder> [--connectivity codex]\n"
        f"\nLicence: {FLYWIRE_LICENSE_NOTE}"
    )


@data.command("fetch")
def data_fetch(
    bundle: str = typer.Argument(..., help="flywire-783 | flywire-630 | skeletons"),
    no_import: bool = typer.Option(False, help="download only"),
):
    """Download an open bundle (checksummed) and import it."""
    from flymind.connectome.importer import import_directory
    from flymind.connectome.sources import BUNDLES, bundle_dir, fetch_bundle

    key = BUNDLE_ALIASES.get(bundle, bundle)
    if key not in BUNDLES:
        raise typer.BadParameter(f"unknown bundle {bundle}; see `flymind data sources`")
    fetch_bundle(key, progress=_echo)
    if key == "flywire-783-skeletons":
        from flymind.visualization.geometry import build_skeleton_index

        out = build_skeleton_index(progress=_echo)
        typer.echo(f"skeleton index ready: {out}")
        return
    if not no_import:
        out = import_directory(bundle_dir(key), BUNDLES[key].dataset_id)
        _print_report(out)


@data.command("import")
def data_import(
    folder: Path,
    dataset: str | None = typer.Option(None, help="dataset id override"),
    connectivity: str = typer.Option("auto", help="auto | shiu | codex"),
):
    """Import a folder of downloaded files (recognised by their headers)."""
    from flymind.connectome.detect import scan_directory
    from flymind.connectome.importer import import_directory

    found = scan_directory(folder)
    if not found:
        raise typer.BadParameter(f"no recognised dataset files in {folder}")
    for f in found:
        typer.echo(f"  detected {f.role:<28} {f.path.name}")
    out = import_directory(folder, dataset, connectivity)
    _print_report(out)


@data.command("fixture")
def data_fixture():
    """Build the small SYNTHETIC demonstration dataset (no download)."""
    from flymind.common.paths import processed_dir
    from flymind.connectome.fixtures import build_fixture

    info = build_fixture(processed_dir())
    typer.echo(
        f"built {info.dataset_id}: {info.n_neurons} neurons, {info.n_edges} edges (synthetic)"
    )


@data.command("validate")
def data_validate(dataset: str | None = typer.Argument(None)):
    """Re-run integrity validation for one or all installed datasets."""
    from flymind.connectome.store import dataset_dir, list_datasets
    from flymind.connectome.validate import validate_and_record

    ids = [dataset] if dataset else [m.dataset_id for m in list_datasets()]
    failed = False
    for d in ids:
        rep = validate_and_record(dataset_dir(d))
        typer.echo(f"{d}: {rep.status}")
        for c in rep.checks:
            if c.status in ("fail", "warn"):
                typer.echo(f"   {c.status.upper()}: {c.name} - {c.message}")
        failed |= rep.status == "failed"
    raise typer.Exit(1 if failed else 0)


@data.command("info")
def data_info(dataset: str | None = typer.Argument(None)):
    """Show installed datasets and their provenance."""
    from flymind.connectome.store import list_datasets

    ms = list_datasets()
    if not ms:
        typer.echo(
            "No datasets installed. Run `uv run flymind data fixture` or "
            "`uv run flymind data fetch flywire-783`."
        )
        return
    for m in ms:
        if dataset and m.dataset_id != dataset:
            continue
        tag = "SYNTHETIC" if m.synthetic else f"v{m.dataset_version}"
        typer.echo(
            f"{m.dataset_id} [{tag}] neurons={m.n_neurons:,} edges={m.n_edges:,} "
            f"synapses={m.n_synapses:,} validation={m.validation_status}"
        )
        if dataset:
            typer.echo(m.model_dump_json(indent=2))


def _print_report(out: Path) -> None:
    typer.echo((out / "validation_report.md").read_text())


# ------------------------------------------------------------------------ sim
@sim.command("run")
def sim_run(
    dataset: str = typer.Option("synthetic_demo_v1"),
    group: list[str] = typer.Option([], help="neuron group(s) to stimulate"),
    root_id: list[int] = typer.Option([], help="root id(s) to stimulate"),
    rate: float = typer.Option(150.0, help="Poisson rate (Hz)"),
    duration_ms: float = typer.Option(1000.0),
    seed: int = typer.Option(0),
    mode: str = typer.Option("full", help="full | demo"),
    top: int = typer.Option(15),
    out: Path | None = typer.Option(None, help="write spikes parquet here"),
):
    """Stimulate neurons and print the most active neurons."""
    import time

    import numpy as np

    from flymind.brain.engine import BrainNetwork, LIFEngine
    from flymind.brain.stimulus import PoissonStimulus
    from flymind.connectome.selectors import NeuronSelector, resolve
    from flymind.connectome.store import get_store

    store = get_store(dataset)
    targets = set()
    for g in group:
        targets |= set(resolve(store, NeuronSelector(group=g)).tolist())
    if root_id:
        targets |= set(store.root_to_idx(root_id).tolist())
    if not targets:
        raise typer.BadParameter("give --group or --root-id")
    net = BrainNetwork.full(store.graph, mode)
    eng = LIFEngine(net, seed=seed)
    eng.add_stimulus(PoissonStimulus(targets=sorted(targets), rate_hz=rate))
    n = int(round(duration_ms / eng.params.dt_ms))
    t0 = time.perf_counter()
    res = eng.run(n)
    wall = time.perf_counter() - t0
    counts = np.bincount(res.spike_local, minlength=net.n)
    nb = store.neurons
    typer.echo(
        f"{dataset}: {net.n:,} neurons, {duration_ms:.0f} ms simulated in {wall:.2f} s "
        f"wall ({duration_ms / 1000 / wall:.2f}x real time); {len(res.spike_steps):,} spikes, "
        f"{int((counts > 0).sum())} active neurons"
    )
    for i in np.argsort(-counts)[:top]:
        if counts[i] == 0:
            break
        typer.echo(
            f"  {int(nb.at[i, 'root_id'])}  {nb.at[i, 'cell_type']!s:<16} "
            f"{counts[i] / duration_ms * 1000:7.1f} Hz"
        )
    if out:
        import pandas as pd

        pd.DataFrame(
            {
                "t_ms": res.spike_steps * eng.params.dt_ms,
                "root_id": nb["root_id"].to_numpy()[res.spike_local],
            }
        ).to_parquet(out)


# ------------------------------------------------------------------------ fly
@fly.command("run")
def fly_run(
    arena: str = typer.Option("empty", help="empty|food|obstacle|light|experimental"),
    controller: str = typer.Option("baseline", help="baseline | neural"),
    dataset: str = typer.Option("synthetic_demo_v1"),
    bridge: str | None = typer.Option(None),
    duration_s: float = typer.Option(2.0),
    forward: float = typer.Option(1.0),
    turn: float = typer.Option(0.0),
    seed: int = typer.Option(0),
    save: bool = typer.Option(True),
):
    """Run a virtual-fly session headless and print behavioural metrics."""
    from flymind.brain.session import NetworkConfig, SessionConfig
    from flymind.embodiment.arena import arena_preset
    from flymind.embodiment.session import BaselineCommand, FlySession, FlySessionConfig

    cfg = FlySessionConfig(
        arena=arena_preset(arena),
        controller=controller,
        duration_s=duration_s,
        seed=seed,
        baseline=BaselineCommand(forward=forward, turn=turn),
        bridge=bridge
        or ("synthetic_demo" if dataset == "synthetic_demo_v1" else "flywire_literature"),
        brain=SessionConfig(dataset_id=dataset, network=NetworkConfig(mode="full"))
        if controller == "neural"
        else None,
    )
    s = FlySession(cfg)
    s.run_blocking()
    typer.echo(json.dumps(s.metrics(), indent=2))
    if s.brain is not None and s.missing_groups:
        typer.echo(f"WARNING: bridge groups missing in this network: {s.missing_groups}")
    typer.echo(f"wall {s.wall_s:.1f} s for {s.body.t_s:.2f} s simulated")
    if save:
        typer.echo(f"saved {s.save()}")


# ---------------------------------------------------------------- experiment
@exp.command("templates")
def exp_templates():
    """List experiment templates and the datasets they are defined for."""
    from flymind.experiments.templates import TEMPLATES

    for key, (title, _fn, ds) in TEMPLATES.items():
        typer.echo(f"{key:<32} {title}\n{'':<32} datasets: {', '.join(ds)}")


@exp.command("run")
def exp_run(
    spec_or_template: str = typer.Argument(..., help="spec.json path or template key"),
    dataset: str = typer.Option("synthetic_demo_v1", help="dataset (for templates)"),
    trials: int | None = typer.Option(None),
    experiment_id: str | None = None,
):
    """Run a template or a saved spec.json; results go to experiments/<id>/."""
    from flymind.experiments.runner import run_experiment
    from flymind.experiments.spec import ExperimentSpec
    from flymind.experiments.templates import build_template

    p = Path(spec_or_template)
    spec = (
        ExperimentSpec.model_validate_json(p.read_text())
        if p.suffix == ".json"
        else build_template(spec_or_template, dataset)
    )
    if trials:
        spec.n_trials = trials
    out = run_experiment(
        spec, experiment_id=experiment_id, progress=lambda f, m: _echo(f"[{f * 100:5.1f}%] {m}")
    )
    typer.echo((out / "README.md").read_text())


@exp.command("list")
def exp_list():
    """List saved experiments."""
    from flymind.common.paths import experiments_dir

    for d in sorted(experiments_dir().glob("*")):
        if (d / "record.json").is_file():
            r = json.loads((d / "record.json").read_text())
            typer.echo(f"{d.name}  [{r.get('evidence')}]  {r.get('name', '')}")


@exp.command("compare")
def exp_compare(a: str, b: str, condition_a: str | None = None, condition_b: str | None = None):
    """Compare two saved experiments (or two conditions: pass the same id twice)."""
    from flymind.common.paths import experiments_dir
    from flymind.experiments.compare import compare_experiments

    res = compare_experiments(
        experiments_dir() / a, experiments_dir() / b, condition_a, condition_b
    )
    typer.echo(json.dumps(res, indent=2, default=str))


# ---------------------------------------------------------------------- serve
@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", help="bind address (localhost by default)"),
    port: int = typer.Option(8000),
    reload: bool = typer.Option(False),
):
    """Start the FlyMind API (and the built web app, if present)."""
    import uvicorn

    if host not in ("127.0.0.1", "localhost", "::1"):
        _echo(
            f"WARNING: binding to {host} exposes the API beyond this machine. The API has no "
            "authentication; only do this on a trusted network."
        )
    uvicorn.run("flymind.api.app:app", host=host, port=port, reload=reload, log_level="info")


@app.command("doctor")
def doctor():
    """Check the environment and print actionable diagnostics."""
    import importlib.util
    import platform

    from flymind.connectome.store import list_datasets

    ok = True
    typer.echo(f"Python {platform.python_version()} on {platform.platform()}")
    for mod in ("numpy", "numba", "brian2", "mujoco", "flygym", "fastapi"):
        found = importlib.util.find_spec(mod) is not None
        ok &= found
        typer.echo(f"  {'ok ' if found else 'MISSING'} {mod}")
    try:
        import mujoco

        m = mujoco.MjModel.from_xml_string("<mujoco><worldbody/></mujoco>")
        typer.echo(f"  ok  MuJoCo {mujoco.__version__} model compiles ({m.nbody} body)")
    except Exception as exc:  # pragma: no cover - environment specific
        ok = False
        typer.echo(f"  FAIL MuJoCo: {exc}")
    ds = list_datasets()
    typer.echo(f"  datasets: {', '.join(m.dataset_id for m in ds) or 'none (run make setup)'}")
    raise typer.Exit(0 if ok else 1)


def main() -> None:  # pragma: no cover
    sys.exit(app())


if __name__ == "__main__":  # pragma: no cover
    main()
