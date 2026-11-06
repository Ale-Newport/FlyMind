"""Compare two experiment results (or two conditions within one experiment)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _load(d: Path) -> tuple[dict, pd.DataFrame | None, pd.DataFrame | None]:
    rec = json.loads((d / "record.json").read_text())
    readouts = pd.read_csv(d / "readouts.csv") if (d / "readouts.csv").is_file() else None
    rates = pd.read_parquet(d / "rates.parquet") if (d / "rates.parquet").is_file() else None
    return rec, readouts, rates


def compare_experiments(
    da: Path, db: Path, cond_a: str | None = None, cond_b: str | None = None, top: int = 30
) -> dict:
    ra, ro_a, rt_a = _load(da)
    rb, ro_b, rt_b = _load(db)
    ds_a = (ra.get("dataset") or {}).get("dataset_id")
    ds_b = (rb.get("dataset") or {}).get("dataset_id")
    warnings = []
    if ds_a != ds_b:
        warnings.append(
            f"different datasets ({ds_a} vs {ds_b}): neuron identities are not "
            "comparable across specimens/releases"
        )
    cond_a = cond_a or (list(ra.get("summary", {})) or [None])[0]
    cond_b = cond_b or (list(rb.get("summary", {})) or [None])[-1]
    out: dict = {
        "a": {"experiment_id": da.name, "condition": cond_a, "evidence": ra.get("evidence")},
        "b": {"experiment_id": db.name, "condition": cond_b, "evidence": rb.get("evidence")},
        "warnings": warnings,
    }
    if ro_a is not None and ro_b is not None:
        a = ro_a[ro_a["condition"] == cond_a].set_index("readout")
        b = ro_b[ro_b["condition"] == cond_b].set_index("readout")
        names = sorted(set(a.index) | set(b.index))
        out["readouts"] = [
            {
                "readout": n,
                "a_mean_hz": float(a.at[n, "mean_rate_hz"]) if n in a.index else None,
                "b_mean_hz": float(b.at[n, "mean_rate_hz"]) if n in b.index else None,
                "a_std_hz": float(a.at[n, "std_hz"]) if n in a.index else None,
                "b_std_hz": float(b.at[n, "std_hz"]) if n in b.index else None,
            }
            for n in names
        ]
        for r in out["readouts"]:
            r["delta_hz"] = (
                None
                if r["a_mean_hz"] is None or r["b_mean_hz"] is None
                else r["b_mean_hz"] - r["a_mean_hz"]
            )
    if rt_a is not None and rt_b is not None and ds_a == ds_b:
        a = rt_a[rt_a["condition"] == cond_a].set_index("root_id")["mean_hz"]
        b = rt_b[rt_b["condition"] == cond_b].set_index("root_id")["mean_hz"]
        both = pd.concat([a.rename("a"), b.rename("b")], axis=1).fillna(0.0)
        both["delta"] = both["b"] - both["a"]
        ct = pd.concat(
            [rt_a.set_index("root_id")["cell_type"], rt_b.set_index("root_id")["cell_type"]]
        )
        ct = ct[~ct.index.duplicated()]
        chg = both.reindex(both["delta"].abs().sort_values(ascending=False).index).head(top)
        out["largest_changes"] = [
            {
                "root_id": str(int(rid)),
                "cell_type": ct.get(rid),
                "a_hz": float(r["a"]),
                "b_hz": float(r["b"]),
                "delta_hz": float(r["delta"]),
            }
            for rid, r in chg.iterrows()
        ]
        out["active"] = {
            "a": int((both["a"] > 0).sum()),
            "b": int((both["b"] > 0).sum()),
            "both": int(((both["a"] > 0) & (both["b"] > 0)).sum()),
        }
    sa, sb = ra.get("summary", {}).get(cond_a, {}), rb.get("summary", {}).get(cond_b, {})
    out["totals"] = {
        "a_spikes_per_trial": sa.get("spikes_per_trial"),
        "b_spikes_per_trial": sb.get("spikes_per_trial"),
    }
    return out
