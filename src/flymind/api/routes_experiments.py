"""Experiment templates, background runs, results, comparison and jobs."""

from __future__ import annotations

import json

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from flymind.common.paths import experiments_dir, safe_join, validate_identifier
from flymind.connectome.store import list_datasets
from flymind.experiments.compare import compare_experiments
from flymind.experiments.runner import new_experiment_id, run_experiment
from flymind.experiments.spec import ExperimentSpec
from flymind.experiments.templates import TEMPLATES, build_template

router = APIRouter(prefix="/api")
ARTIFACTS = {
    "spec.json",
    "record.json",
    "README.md",
    "spikes.parquet",
    "rates.parquet",
    "readouts.csv",
    "timecourse.csv",
    "regions.csv",
    "trajectory.parquet",
    "joints.parquet",
    "probes.parquet",
}


@router.get("/experiments/templates")
def templates(dataset_id: str | None = None):
    installed = {m.dataset_id for m in list_datasets()}
    out = []
    for key, (title, _fn, datasets) in TEMPLATES.items():
        for ds in datasets:
            if dataset_id and ds != dataset_id:
                continue
            available = ds in installed
            spec = build_template(key, ds) if available else None
            out.append(
                {
                    "key": key,
                    "title": title,
                    "dataset_id": ds,
                    "available": available,
                    "spec": spec.model_dump() if spec else None,
                }
            )
    return out


class RunIn(BaseModel):
    spec: ExperimentSpec


@router.post("/experiments/run")
def run(request: Request, body: RunIn):
    jobs = request.app.state.service.jobs
    exp_id = new_experiment_id(body.spec.name)

    def task(job):
        def progress(frac, msg):
            job.progress, job.message = frac, msg

        out = run_experiment(body.spec, progress=progress, cancel=job.cancel, experiment_id=exp_id)
        return {"experiment_id": out.name}

    job = jobs.submit("experiment", body.spec.name, task)
    return {"job_id": job.id, "experiment_id": exp_id}


@router.get("/experiments")
def list_experiments():
    root = experiments_dir()
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir(), reverse=True):
        rec = d / "record.json"
        if not rec.is_file():
            continue
        try:
            r = json.loads(rec.read_text())
        except json.JSONDecodeError:
            continue
        out.append(
            {
                "experiment_id": d.name,
                "name": r.get("name") or r.get("config", {}).get("label") or d.name,
                "kind": r.get("kind", "experiment"),
                "template": r.get("template"),
                "created_at": r.get("created_at"),
                "evidence": r.get("evidence"),
                "dataset_id": (r.get("dataset") or {}).get("dataset_id")
                or ((r.get("config") or {}).get("brain") or {}).get("dataset_id"),
                "conditions": list((r.get("summary") or {}).keys()),
            }
        )
    return out


def _exp_dir(eid: str):
    validate_identifier(eid, "experiment id")
    d = safe_join(experiments_dir(), eid)
    if not (d / "record.json").is_file():
        raise HTTPException(404, f"no experiment {eid}")
    return d


@router.get("/experiments/{eid}")
def experiment(eid: str):
    d = _exp_dir(eid)
    out = {
        "record": json.loads((d / "record.json").read_text()),
        "files": sorted(p.name for p in d.iterdir() if p.name in ARTIFACTS),
    }
    if (d / "spec.json").is_file():
        out["spec"] = json.loads((d / "spec.json").read_text())
    for name in ("readouts", "timecourse", "regions"):
        p = d / f"{name}.csv"
        if p.is_file():
            out[name] = pd.read_csv(p).to_dict(orient="records")
    sub = sorted(p.name for p in d.iterdir() if p.is_dir() and p.name.startswith("fly_"))
    out["embodied_runs"] = sub
    return out


@router.get("/experiments/{eid}/files/{name}")
def experiment_file(eid: str, name: str):
    d = _exp_dir(eid)
    if name not in ARTIFACTS:
        raise HTTPException(404, "unknown artifact")
    p = safe_join(d, name)
    if not p.is_file():
        raise HTTPException(404, "artifact not present")
    return FileResponse(p, filename=f"{eid}_{name}")


@router.get("/experiments/{eid}/runs/{run}/trajectory")
def embodied_trajectory(eid: str, run: str):
    d = _exp_dir(eid)
    validate_identifier(run, "run")
    p = safe_join(d, run, "trajectory.parquet")
    if not p.is_file():
        raise HTTPException(404, "no trajectory")
    df = pd.read_parquet(p)
    if len(df) > 2000:
        df = df.iloc[:: len(df) // 2000 + 1]
    return {"rows": df.round(5).to_dict("records")}


class CompareIn(BaseModel):
    a: str
    b: str
    condition_a: str | None = None
    condition_b: str | None = None


@router.post("/experiments/compare")
def compare(body: CompareIn):
    da, db = _exp_dir(body.a), _exp_dir(body.b)
    try:
        return compare_experiments(da, db, body.condition_a, body.condition_b)
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/jobs")
def jobs(request: Request):
    return [j.public() for j in request.app.state.service.jobs.jobs.values()]


@router.get("/jobs/{job_id}")
def job(request: Request, job_id: str):
    try:
        return request.app.state.service.jobs.get(job_id).public()
    except KeyError:
        raise HTTPException(404, f"no job {job_id}") from None


@router.post("/jobs/{job_id}/cancel")
def cancel(request: Request, job_id: str):
    try:
        j = request.app.state.service.jobs.get(job_id)
    except KeyError:
        raise HTTPException(404, f"no job {job_id}") from None
    j.cancel.set()
    return j.public()
