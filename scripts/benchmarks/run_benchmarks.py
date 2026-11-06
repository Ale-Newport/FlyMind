"""Measure FlyMind performance and write docs/evidence/benchmarks/<date>.json + .md.

Every number in the output is measured by this script on the machine it runs on; the
machine description and the exact command are recorded with the results.

    uv run python scripts/benchmarks/run_benchmarks.py [--quick] [--brian2-full]
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "evidence" / "benchmarks"


def peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if sys.platform == "darwin" else r / 1e3  # bytes on macOS, KiB on Linux


def timed(fn, *a, **k):
    t = time.perf_counter()
    out = fn(*a, **k)
    return out, time.perf_counter() - t


def bench_lif(store, nodes, stim_groups, sim_ms, backend="numba", label=""):
    from flymind.brain.engine import BrainNetwork, LIFEngine
    from flymind.brain.stimulus import PoissonStimulus
    from flymind.connectome.selectors import NeuronSelector, resolve

    graph = store.graph
    net = BrainNetwork.full(graph) if nodes is None else BrainNetwork.subset(graph, nodes)
    eng = LIFEngine(net, seed=0, backend=backend)
    for g in stim_groups:
        eng.add_stimulus(
            PoissonStimulus(targets=resolve(store, NeuronSelector(group=g)).tolist(), rate_hz=200)
        )
    eng.run(10)  # JIT warm-up (compile time excluded and reported separately)
    eng.reset(0)
    n_steps = int(sim_ms / eng.params.dt_ms)
    res, wall = timed(eng.run, n_steps)
    return {
        "label": label,
        "backend": backend,
        "neurons": net.n,
        "edges": net.graph.n_edges,
        "simulated_s": sim_ms / 1000,
        "wall_s": round(wall, 4),
        "steps_per_s": round(n_steps / wall, 1),
        "sim_s_per_wall_s": round(sim_ms / 1000 / wall, 4),
        "spikes": int(len(res.spike_steps)),
        "active_neurons": int(len(np.unique(res.spike_local))),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="shorter runs")
    ap.add_argument("--brian2-full", action="store_true", help="also time Brian2 on the full brain")
    args = ap.parse_args()
    from flymind.common.provenance import machine_info, package_versions
    from flymind.connectome.store import ConnectomeStore, DatasetNotFoundError, clear_store_cache

    sim_ms = 300 if args.quick else 1000
    results: dict = {
        "command": "uv run python scripts/benchmarks/run_benchmarks.py " + " ".join(sys.argv[1:]),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "machine": machine_info(),
        "packages": package_versions(),
        "measurements": {},
    }
    m = results["measurements"]

    # ------------------------------------------------------------------ data
    import tempfile

    from flymind.connectome.fixtures import build_fixture

    tmp = Path(tempfile.mkdtemp())
    _, m["fixture_build_s"] = timed(build_fixture, tmp)
    fixture = ConnectomeStore(tmp / "synthetic_demo_v1")
    try:
        clear_store_cache()
        t = time.perf_counter()
        real = ConnectomeStore.open("flywire_fafb_783", root=ROOT / "data" / "processed")
        _ = real.neurons
        _ = real.graph.indptr[-1]
        m["flywire_783_load_s"] = round(time.perf_counter() - t, 3)
    except DatasetNotFoundError:
        real = None
        m["flywire_783"] = "BLOCKED: dataset not imported (make data-flywire)"
    raw = ROOT / "data" / "raw" / "flywire-783-open"
    if real is not None and raw.is_dir() and not args.quick:
        from flymind.connectome.importer import import_directory

        out = Path(tempfile.mkdtemp())
        _, m["flywire_783_import_s"] = timed(
            import_directory, raw, "flywire_fafb_783", out_root=out
        )
        m["flywire_783_import_note"] = "includes validation; raw files already downloaded"

    # ------------------------------------------------------------------ brain
    lif = m["lif"] = []
    lif.append(
        bench_lif(
            fixture,
            None,
            ["orn_attr_l", "grn_sugar"],
            sim_ms,
            "numba",
            "synthetic fixture (demo mode)",
        )
    )
    lif.append(
        bench_lif(
            fixture,
            None,
            ["orn_attr_l", "grn_sugar"],
            sim_ms,
            "numpy",
            "synthetic fixture (demo mode)",
        )
    )
    if real is not None:
        from flymind.connectome.selectors import NeuronSelector, resolve

        lif.append(
            bench_lif(
                real,
                None,
                ["sugar_grn_shiu"],
                sim_ms,
                "numba",
                "FlyWire v783 full brain, sugar GRNs 200 Hz",
            )
        )
        region = resolve(real, NeuronSelector(neuropils=["AL_L", "AL_R", "LH_L", "LH_R"]))
        lif.append(
            bench_lif(
                real,
                region,
                ["orn_dm1_left"],
                sim_ms,
                "numba",
                "FlyWire v783 region mode (AL + LH)",
            )
        )
        lif.append(
            bench_lif(
                real,
                None,
                ["orn_dm1_left", "orn_dm1_right"],
                sim_ms,
                "numba",
                "FlyWire v783 full brain, DM1 ORNs 200 Hz",
            )
        )
    m["peak_rss_mb_after_brain"] = round(peak_rss_mb(), 1)

    # Brian2 reference on the fixture (code generation + run, cython)
    from flymind.brain.brian2_engine import run_brian2
    from flymind.brain.engine import BrainNetwork, LIFEngine
    from flymind.brain.stimulus import PoissonStimulus
    from flymind.connectome.selectors import NeuronSelector, resolve

    eng = LIFEngine(BrainNetwork.full(fixture.graph), seed=0)
    orn = resolve(fixture, NeuronSelector(group="orn_attr_l")).tolist()
    eng.add_stimulus(PoissonStimulus(targets=orn, rate_hz=200))
    b = run_brian2(eng, int(sim_ms / 0.1), codegen="cython")
    m["brian2_fixture"] = {
        "build_s": round(b.wall_build_s, 3),
        "run_s": round(b.wall_run_s, 3),
        "simulated_s": sim_ms / 1000,
        "codegen": "cython",
    }
    if args.brian2_full and real is not None:
        eng = LIFEngine(BrainNetwork.full(real.graph), seed=0)
        sugar = resolve(real, NeuronSelector(group="sugar_grn_shiu")).tolist()
        eng.add_stimulus(PoissonStimulus(targets=sugar, rate_hz=200))
        b = run_brian2(eng, int(sim_ms / 0.1), codegen="cython")
        m["brian2_flywire_783_full"] = {
            "build_s": round(b.wall_build_s, 1),
            "run_s": round(b.wall_run_s, 2),
            "simulated_s": sim_ms / 1000,
        }

    # ---------------------------------------------------------------- physics
    from flymind.brain.session import NetworkConfig, SessionConfig, SimulationSession
    from flymind.embodiment.arena import arena_preset
    from flymind.embodiment.session import FlySession, FlySessionConfig

    phys = m["virtual_fly"] = []
    dur = 0.5 if args.quick else 1.0
    s, build = timed(FlySession, FlySessionConfig(arena=arena_preset("empty"), duration_s=dur))
    _, wall = timed(s.run_blocking)
    phys.append(
        {
            "label": "baseline controller, empty arena",
            "model_build_s": round(build, 2),
            "simulated_s": dur,
            "wall_s": round(wall, 2),
            "sim_s_per_wall_s": round(dur / wall, 3),
            "physics_steps_per_s": round(dur / s.body.dt_s / wall, 1),
        }
    )
    s, build = timed(FlySession, FlySessionConfig(arena=arena_preset("light"), duration_s=dur))
    _, wall = timed(s.run_blocking)
    phys.append(
        {
            "label": "baseline controller, light arena (compound-eye vision at 20 Hz)",
            "simulated_s": dur,
            "wall_s": round(wall, 2),
            "sim_s_per_wall_s": round(dur / wall, 3),
        }
    )
    s = FlySession(
        FlySessionConfig(
            arena=arena_preset("food"),
            controller="neural",
            duration_s=dur,
            brain=SessionConfig(dataset_id="synthetic_demo_v1", network=NetworkConfig(mode="demo")),
        ),
        brain_factory=lambda cfg: SimulationSession(cfg, store=fixture),
    )
    _, wall = timed(s.run_blocking)
    phys.append(
        {
            "label": "neural controller, synthetic network, food arena",
            "simulated_s": dur,
            "wall_s": round(wall, 2),
            "sim_s_per_wall_s": round(dur / wall, 3),
            "bridge_interval_ms": s.bridge.interval_ms,
            "wall_ms_per_bridge_interval": round(
                wall / (dur * 1000 / s.bridge.interval_ms) * 1000, 3
            ),
        }
    )
    if real is not None:
        s = FlySession(
            FlySessionConfig(
                arena=arena_preset("food"),
                controller="neural",
                duration_s=dur,
                bridge="flywire_literature",
                brain=SessionConfig(
                    dataset_id="flywire_fafb_783", network=NetworkConfig(mode="full")
                ),
            ),
            brain_factory=lambda cfg: SimulationSession(cfg, store=real),
        )
        _, wall = timed(s.run_blocking)
        phys.append(
            {
                "label": "neural controller, FlyWire v783 full brain, food arena",
                "simulated_s": dur,
                "wall_s": round(wall, 2),
                "sim_s_per_wall_s": round(dur / wall, 3),
                "bridge_interval_ms": s.bridge.interval_ms,
                "wall_ms_per_bridge_interval": round(
                    wall / (dur * 1000 / s.bridge.interval_ms) * 1000, 3
                ),
            }
        )
    m["peak_rss_mb_total"] = round(peak_rss_mb(), 1)

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    (OUT / f"{stamp}.json").write_text(json.dumps(results, indent=2) + "\n")
    lines = [
        f"# Benchmark run {results['date']}",
        "",
        f"Command: `{results['command']}`",
        "",
        f"Machine: {results['machine'].get('cpu_model', results['machine']['processor'])}, "
        f"{results['machine'].get('cpu_count')} cores, "
        f"{round(results['machine'].get('memory_bytes', 0) / 2**30)} GiB RAM, "
        f"{results['machine']['platform']}",
        "",
        "## LIF engine",
        "",
        "| Network | Backend | Neurons | Edges | Simulated | Wall | Sim s / wall s "
        "| Steps/s | Spikes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in lif:
        lines.append(
            f"| {r['label']} | {r['backend']} | {r['neurons']:,} | {r['edges']:,} | "
            f"{r['simulated_s']} s | {r['wall_s']} s | {r['sim_s_per_wall_s']} | "
            f"{r['steps_per_s']:,} | {r['spikes']:,} |"
        )
    lines += [
        "",
        "## Virtual fly (MuJoCo + controller [+ brain])",
        "",
        "| Configuration | Simulated | Wall | Sim s / wall s |",
        "|---|---|---|---|",
    ]
    for r in phys:
        lines.append(
            f"| {r['label']} | {r['simulated_s']} s | {r['wall_s']} s | {r['sim_s_per_wall_s']} |"
        )
    lines += [
        "",
        "## Other",
        "",
        "```json",
        json.dumps({k: v for k, v in m.items() if k not in ("lif", "virtual_fly")}, indent=2),
        "```",
        "",
    ]
    (OUT / f"{stamp}.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
