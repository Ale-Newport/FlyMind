"""Re-create figures from a saved experiment directory (readouts, time course, regions).

uv run python scripts/validation/plot_experiment.py experiments/<id> [--out figs/]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("experiment", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    d = a.experiment
    out = a.out or d / "figures"
    out.mkdir(parents=True, exist_ok=True)
    rec = json.loads((d / "record.json").read_text())
    label = f"{rec.get('name')} [{rec.get('evidence')}]"
    if (d / "readouts.csv").is_file():
        ro = pd.read_csv(d / "readouts.csv")
        piv = ro.pivot(index="condition", columns="readout", values="mean_rate_hz")
        err = ro.pivot(index="condition", columns="readout", values="std_hz")
        ax = piv.plot.bar(yerr=err, capsize=3, figsize=(7, 4), rot=0)
        for c in rec.get("expected_checks", []):
            ax.axhline(c["value_hz"], ls="--", lw=1, color="k", alpha=0.5)
        ax.set_ylabel("rate (Hz, mean ± SD over trials)")
        ax.set_title(label, fontsize=9)
        plt.tight_layout()
        plt.savefig(out / "readouts.png", dpi=150)
        plt.close()
    if (d / "timecourse.csv").is_file():
        tc = pd.read_csv(d / "timecourse.csv")
        _fig, ax = plt.subplots(figsize=(7, 4))
        for (cond, rd), g in tc.groupby(["condition", "readout"]):
            ax.plot(g["t_ms"], g["rate_hz"], label=f"{cond} · {rd}", lw=1)
        ax.set_xlabel("time (ms)")
        ax.set_ylabel("rate (Hz)")
        ax.legend(fontsize=7)
        ax.set_title(label, fontsize=9)
        plt.tight_layout()
        plt.savefig(out / "timecourse.png", dpi=150)
        plt.close()
    for run in sorted(d.glob("fly_*")):
        tr = pd.read_parquet(run / "trajectory.parquet")
        plt.plot(tr["x_mm"], tr["y_mm"], label=run.name)
    if any(d.glob("fly_*")):
        plt.gca().set_aspect("equal")
        plt.xlabel("x (mm)")
        plt.ylabel("y (mm)")
        plt.legend(fontsize=7)
        plt.title(label, fontsize=9)
        plt.savefig(out / "trajectories.png", dpi=150)
        plt.close()
    print(f"figures written to {out}")


if __name__ == "__main__":
    main()
