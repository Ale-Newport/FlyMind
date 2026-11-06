"""Spike/probe recording and analysis (rates, population activity, regional activity)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class SpikeRecord:
    """Append-only spike store in dataset idx and absolute steps (thread-safe)."""

    dt_ms: float
    _steps: list[np.ndarray] = field(default_factory=list)
    _idx: list[np.ndarray] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _cache: tuple[np.ndarray, np.ndarray] | None = None

    def append(self, steps: np.ndarray, idx: np.ndarray) -> None:
        if len(steps) == 0:
            return
        with self._lock:
            self._steps.append(np.asarray(steps, dtype=np.int64))
            self._idx.append(np.asarray(idx, dtype=np.int64))
            self._cache = None

    def clear(self) -> None:
        with self._lock:
            self._steps.clear()
            self._idx.clear()
            self._cache = None

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        with self._lock:
            if self._cache is None:
                if self._steps:
                    self._cache = (np.concatenate(self._steps), np.concatenate(self._idx))
                    self._steps, self._idx = [self._cache[0]], [self._cache[1]]
                else:
                    z = np.zeros(0, dtype=np.int64)
                    self._cache = (z, z)
            return self._cache

    def __len__(self) -> int:
        return len(self.arrays()[0])

    def window(self, t0_ms: float, t1_ms: float) -> tuple[np.ndarray, np.ndarray]:
        steps, idx = self.arrays()
        lo, hi = np.searchsorted(steps, [t0_ms / self.dt_ms, t1_ms / self.dt_ms])
        return steps[lo:hi], idx[lo:hi]

    def counts(self, n: int, t0_ms: float = 0.0, t1_ms: float = np.inf) -> np.ndarray:
        _, idx = self.window(t0_ms, t1_ms)
        return np.bincount(idx, minlength=n)

    def rates_hz(self, n: int, t0_ms: float, t1_ms: float) -> np.ndarray:
        dur_s = max(t1_ms - t0_ms, 1e-9) / 1000.0
        return self.counts(n, t0_ms, t1_ms) / dur_s

    def to_frame(self, root_ids: np.ndarray) -> pd.DataFrame:
        steps, idx = self.arrays()
        return pd.DataFrame(
            {
                "t_ms": steps * self.dt_ms,
                "step": steps,
                "idx": idx.astype(np.int32),
                "root_id": root_ids[idx] if len(idx) else np.zeros(0, dtype=np.int64),
            }
        )


def population_rate(
    steps: np.ndarray,
    idx: np.ndarray,
    members: np.ndarray,
    t0_ms: float,
    t1_ms: float,
    bin_ms: float,
    dt_ms: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Mean per-neuron rate (Hz) of ``members`` in bins; returns (bin centres ms, rates)."""
    edges = np.arange(t0_ms, t1_ms + bin_ms * 0.5, bin_ms)
    if len(edges) < 2 or len(members) == 0:
        return np.zeros(0), np.zeros(0)
    sel = np.isin(idx, members)
    hist, _ = np.histogram(steps[sel] * dt_ms, bins=edges)
    return (edges[:-1] + edges[1:]) / 2, hist / (len(members) * bin_ms / 1000.0)


def grouped_activity(
    counts: np.ndarray, labels: pd.Series, duration_ms: float, top: int = 40
) -> list[dict]:
    """Per-label (e.g. neuropil or super class) spike totals and mean rates."""
    df = pd.DataFrame({"label": labels.fillna("unassigned").to_numpy(), "count": counts})
    g = df.groupby("label")["count"].agg(["sum", "size"])
    g = g[g["sum"] > 0].sort_values("sum", ascending=False).head(top)
    dur_s = max(duration_ms, 1e-9) / 1000.0
    return [
        {
            "label": str(k),
            "spikes": int(r["sum"]),
            "neurons": int(r["size"]),
            "mean_rate_hz": float(r["sum"] / r["size"] / dur_s),
        }
        for k, r in g.iterrows()
    ]


def trial_rates(spikes: pd.DataFrame, duration_ms: float, n_trials: int) -> pd.DataFrame:
    """Shiu et al. ``get_rate`` convention: per-trial rate, mean and std (ddof=0) over trials,
    counting trials without spikes as 0 Hz."""
    dur_s = duration_ms / 1000.0
    per = spikes.groupby(["root_id", "trial"]).size().unstack(fill_value=0)
    per = per.reindex(columns=range(n_trials), fill_value=0) / dur_s
    return pd.DataFrame({"mean_hz": per.mean(axis=1), "std_hz": per.std(axis=1, ddof=0)})
