"""Run an :class:`ExperimentSpec` and persist results with full provenance."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from flymind.brain.engine import LIFEngine
from flymind.brain.recording import grouped_activity, trial_rates
from flymind.brain.session import SessionConfig, build_network
from flymind.common.logging import get_logger
from flymind.common.paths import experiments_dir, safe_join, validate_identifier
from flymind.common.provenance import runtime_provenance, utc_now
from flymind.connectome.selectors import resolve
from flymind.connectome.store import ConnectomeStore, get_store
from flymind.experiments.spec import ExperimentSpec

log = get_logger("experiments.runner")
CHUNK_STEPS = 1000


class Cancelled(Exception):
    pass


def new_experiment_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "experiment"
    return f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}_{slug}_{uuid.uuid4().hex[:6]}"


def _targets(store: ConnectomeStore, local_of: np.ndarray, sel) -> list[int]:
    idx = resolve(store, sel)
    idx = idx[local_of[idx] >= 0]
    if len(idx) == 0:
        raise ValueError(
            f"selector matched no simulated neurons: {sel.model_dump(exclude_defaults=True)}"
        )
    return idx.tolist()


def run_experiment(
    spec: ExperimentSpec,
    out_root: Path | None = None,
    progress=None,
    cancel: threading.Event | None = None,
    experiment_id: str | None = None,
) -> Path:
    t_start = time.perf_counter()
    store = get_store(spec.dataset_id)
    exp_id = validate_identifier(experiment_id or new_experiment_id(spec.name), "experiment id")
    out = safe_join(out_root or experiments_dir(), exp_id)
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(spec.model_dump_json(indent=2) + "\n")
    network = build_network(store, spec.network)
    root_ids = store.neurons["root_id"].to_numpy(dtype=np.int64)
    readouts = {
        r.name: np.array(_targets(store, network.local_of, r.selector)) for r in spec.readouts
    }
    resolved: dict[str, object] = {
        "readouts": {k: root_ids[v].tolist() for k, v in readouts.items()}
    }

    spike_frames, rate_frames, read_rows, tc_rows, region_rows = [], [], [], [], []
    summary: dict[str, dict] = {}
    timing: list[dict] = []
    total_runs = len(spec.conditions) * (1 if spec.embodiment else spec.n_trials)
    done_runs = 0
    nb = store.neurons
    region_col = (
        nb["primary_neuropil"] if nb["primary_neuropil"].notna().any() else nb["super_class"]
    )

    for cond in spec.conditions:
        params = spec.params.model_copy(
            update={k: v for k, v in cond.params.items() if k in type(spec.params).model_fields}
        )
        stimuli = [
            s.to_stimulus(_targets(store, network.local_of, s.selector)) for s in cond.stimuli
        ]
        interventions = []
        for iv in cond.interventions:
            post = _targets(store, network.local_of, iv.post_selector) if iv.post_selector else None
            interventions.append(
                iv.to_intervention(_targets(store, network.local_of, iv.selector), post)
            )
        resolved[cond.name] = {
            "stimuli": [
                {"label": s.label, "root_ids": root_ids[st.targets].tolist()}
                for s, st in zip(cond.stimuli, stimuli, strict=True)
            ],
            "interventions": [
                {
                    "label": i.label,
                    "root_ids": root_ids[it.targets if hasattr(it, "targets") else it.pre].tolist(),
                }
                for i, it in zip(cond.interventions, interventions, strict=True)
            ],
            "params": params.model_dump(),
        }
        if spec.embodiment is not None:
            _run_embodied(spec, cond, params, out, resolved)
            done_runs += 1
            if progress:
                progress(done_runs / total_runs, f"{cond.name}: embodied run complete")
            continue

        n_steps = int(round(spec.duration_ms / params.dt_ms))
        cond_spikes = []
        for trial in range(spec.n_trials):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            engine = LIFEngine(network, params, seed=spec.seed + trial, backend=spec.backend)
            engine.set_stimuli(stimuli)
            engine.set_interventions(interventions)
            t0 = time.perf_counter()
            steps_l, idx_l = [], []
            remaining = n_steps
            while remaining > 0:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                res = engine.run(min(CHUNK_STEPS, remaining))
                remaining -= res.n_steps
                steps_l.append(res.spike_steps)
                idx_l.append(network.global_idx[res.spike_local])
            wall = time.perf_counter() - t0
            timing.append(
                {
                    "condition": cond.name,
                    "trial": trial,
                    "wall_s": wall,
                    "sim_s": spec.duration_ms / 1000,
                    "sim_wall_ratio": (spec.duration_ms / 1000) / wall if wall else None,
                }
            )
            steps = np.concatenate(steps_l)
            gidx = np.concatenate(idx_l)
            cond_spikes.append(
                pd.DataFrame(
                    {
                        "condition": cond.name,
                        "trial": np.int16(trial),
                        "t_ms": (steps * params.dt_ms).astype(np.float32),
                        "idx": gidx.astype(np.int32),
                        "root_id": root_ids[gidx],
                    }
                )
            )
            done_runs += 1
            if progress:
                progress(done_runs / total_runs, f"{cond.name}: trial {trial + 1}/{spec.n_trials}")
        sp = pd.concat(cond_spikes, ignore_index=True)
        spike_frames.append(sp)
        rates = trial_rates(sp, spec.duration_ms, spec.n_trials).reset_index()
        rates.insert(0, "condition", cond.name)
        rates["cell_type"] = (
            nb["cell_type"].to_numpy()[store.root_to_idx(rates["root_id"].to_numpy())]
            if len(rates)
            else []
        )
        rate_frames.append(rates)
        counts = np.bincount(sp["idx"], minlength=len(nb)) / spec.n_trials
        cond_sum = {
            "spikes_per_trial": float(len(sp) / spec.n_trials),
            "active_neurons_any_trial": int(sp["idx"].nunique()),
            "readouts": {},
        }
        for name, members in readouts.items():
            per_trial = (
                sp[sp["idx"].isin(members)]
                .groupby("trial")
                .size()
                .reindex(range(spec.n_trials), fill_value=0)
                .to_numpy()
                / len(members)
                / (spec.duration_ms / 1000)
            )
            row = {
                "condition": cond.name,
                "readout": name,
                "n_neurons": len(members),
                "mean_rate_hz": float(per_trial.mean()),
                "std_hz": float(per_trial.std()),
                "per_trial_hz": per_trial.round(4).tolist(),
            }
            read_rows.append(row)
            cond_sum["readouts"][name] = {
                k: row[k] for k in ("mean_rate_hz", "std_hz", "n_neurons")
            }
            edges = np.arange(0, spec.duration_ms + spec.bin_ms * 0.5, spec.bin_ms)
            sel = sp["idx"].isin(members).to_numpy()
            hist, _ = np.histogram(sp["t_ms"].to_numpy()[sel], bins=edges)
            rate = hist / (len(members) * spec.n_trials * spec.bin_ms / 1000)
            tc_rows += [
                {"condition": cond.name, "readout": name, "t_ms": float(t), "rate_hz": float(r)}
                for t, r in zip((edges[:-1] + edges[1:]) / 2, rate, strict=True)
            ]
        for reg in grouped_activity(counts, region_col, spec.duration_ms, top=60):
            region_rows.append({"condition": cond.name, **reg})
        summary[cond.name] = cond_sum

    if spike_frames:
        pd.concat(spike_frames, ignore_index=True).to_parquet(out / "spikes.parquet", index=False)
        pd.concat(rate_frames, ignore_index=True).to_parquet(out / "rates.parquet", index=False)
        pd.DataFrame(read_rows).to_csv(out / "readouts.csv", index=False)
        pd.DataFrame(tc_rows).to_csv(out / "timecourse.csv", index=False)
        pd.DataFrame(region_rows).to_csv(out / "regions.csv", index=False)

    checks = []
    for exp in spec.expected:
        obs = summary.get(exp.condition, {}).get("readouts", {}).get(exp.readout)
        if obs is None:
            checks.append({**exp.model_dump(), "observed_hz": None, "status": "not_run"})
            continue
        ok = abs(obs["mean_rate_hz"] - exp.value_hz) <= exp.tolerance_hz
        checks.append(
            {
                **exp.model_dump(),
                "observed_hz": obs["mean_rate_hz"],
                "observed_std_hz": obs["std_hz"],
                "status": "pass" if ok else "fail",
            }
        )
    evidence = spec.evidence
    if checks and all(c["status"] == "pass" for c in checks):
        evidence = "reproduced"
    record = {
        "experiment_id": exp_id,
        "name": spec.name,
        "template": spec.template,
        "created_at": utc_now(),
        "evidence": evidence,
        "dataset": {
            "dataset_id": store.manifest.dataset_id,
            "version": store.manifest.dataset_version,
            "synthetic": store.manifest.synthetic,
            "files": [f.model_dump() for f in store.manifest.files],
            "n_neurons": store.manifest.n_neurons,
            "n_edges": store.manifest.n_edges,
        },
        "network": {"mode": network.mode, "n_neurons": network.n, "n_edges": network.graph.n_edges},
        "seeds": {
            "base": spec.seed,
            "trial_seeds": [spec.seed + t for t in range(spec.n_trials)],
            "rule": "trial k uses seed base+k in every condition (common random numbers)",
        },
        "model": f"LIF (Shiu et al. 2024 equations), FlyMind engine backend={spec.backend}",
        "assumptions": spec.assumptions,
        "resolved_neurons": resolved,
        "summary": summary,
        "expected_checks": checks,
        "timing": timing,
        "wall_total_s": time.perf_counter() - t_start,
        "runtime": runtime_provenance(),
    }
    (out / "record.json").write_text(json.dumps(record, indent=2, default=_json) + "\n")
    (out / "README.md").write_text(_readme(spec, record))
    return out


def _run_embodied(spec: ExperimentSpec, cond, params, out: Path, resolved: dict) -> None:
    from flymind.embodiment.session import FlySession

    fly_cfg = spec.embodiment.model_copy(deep=True)
    controller = cond.params.get("controller", fly_cfg.controller)
    fly_cfg.controller = controller
    fly_cfg.label = cond.name
    if controller == "neural":
        fly_cfg.brain = SessionConfig(
            dataset_id=spec.dataset_id,
            network=spec.network,
            params=params,
            seed=spec.seed,
            stimuli=cond.stimuli,
            interventions=cond.interventions,
        )
    session = FlySession(fly_cfg)
    session.run_blocking()
    sub = session.save(out / "fly")
    target = out / f"fly_{re.sub(r'[^a-z0-9]+', '-', cond.name.lower())}"
    sub.rename(target)
    if (out / "fly").is_dir() and not any((out / "fly").iterdir()):
        (out / "fly").rmdir()
    resolved[cond.name]["embodied"] = {
        "metrics": session.metrics(),
        "dir": target.name,
        "missing_groups": getattr(session, "missing_groups", []),
    }


def _json(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _readme(spec: ExperimentSpec, record: dict) -> str:
    lines = [
        f"# {spec.name}",
        "",
        spec.description,
        "",
        f"- Experiment ID: `{record['experiment_id']}`",
        f"- Dataset: `{record['dataset']['dataset_id']}` (v{record['dataset']['version']})"
        + (" - SYNTHETIC" if record["dataset"]["synthetic"] else ""),
        f"- Evidence category: **{record['evidence']}**",
        f"- Network: {record['network']['mode']}, {record['network']['n_neurons']} neurons",
        f"- Trials: {spec.n_trials} x {spec.duration_ms} ms, base seed {spec.seed}",
        "",
        "## Readouts",
        "",
        "| Condition | Readout | Mean rate (Hz) | SD across trials |",
        "|---|---|---|---|",
    ]
    for cname, cs in record["summary"].items():
        for rname, r in cs["readouts"].items():
            lines.append(f"| {cname} | {rname} | {r['mean_rate_hz']:.2f} | {r['std_hz']:.2f} |")
    if record["expected_checks"]:
        lines += [
            "",
            "## Comparison with reference values",
            "",
            "| Readout | Condition | Reference (Hz) | Observed (Hz) | Tolerance | Status "
            "| Source |",
            "|---|---|---|---|---|---|---|",
        ]
        for c in record["expected_checks"]:
            obs = "n/a" if c["observed_hz"] is None else f"{c['observed_hz']:.2f}"
            lines.append(
                f"| {c['readout']} | {c['condition']} | {c['value_hz']} | {obs} | "
                f"+-{c['tolerance_hz']} | {c['status']} | {c['source']} |"
            )
    if spec.assumptions:
        lines += ["", "## Assumptions", ""] + [f"- {a}" for a in spec.assumptions]
    lines += [
        "",
        "Reproduce with:",
        "",
        "```bash",
        f"uv run flymind experiment run experiments/{record['experiment_id']}/spec.json",
        "```",
        "",
    ]
    return "\n".join(lines)
