# Benchmarks

All numbers were measured by `scripts/benchmarks/run_benchmarks.py` at commit
`a4e2bcd`, with no other workload running. Raw output:
[`2026-11-06.md`](benchmarks/2026-11-06.md) and the JSON next to it, which
includes package versions and the machine description.

**Machine:** Apple M2 Max (12 cores), 64 GiB RAM, macOS 27.0.1, Python 3.13.16. All
kernels are single-threaded CPU code; there is no GPU.

## Neural simulation (1 s simulated, dt = 0.1 ms, Numba unless stated)

| Network | Neurons | Connections | Wall time | Sim s / wall s | Steps / s | Spikes |
|---|---|---|---|---|---|---|
| FlyWire v783 full brain, sugar GRNs at 200 Hz | 139,255 | 15,091,983 | 2.24 s | **0.45** | 4,470 | 15,830 |
| FlyWire v783 full brain, DM1 ORNs at 200 Hz | 139,255 | 15,091,983 | 2.76 s | 0.36 | 3,623 | 488,737 |
| FlyWire v783 region mode (AL + LH) | 4,433 | 347,857 | 0.26 s | 3.83 | 38,313 | 188,705 |
| Synthetic fixture | 1,114 | 12,185 | 0.022 s | 45.9 | 459,287 | 13,972 |
| Synthetic fixture, NumPy reference kernel | 1,114 | 12,185 | 0.61 s | 1.64 | 16,382 | 13,972 |
| Synthetic fixture, Brian2 2.11 (Cython) | 1,114 | 12,185 | 0.34 s run (+0.26 s build) | 2.9 | — | — |

Per-step cost on the full brain scales with the number of neurons (integration) plus
spikes × out-degree (event-driven delivery). That is why the DM1 run, which has 31× more
spikes, is 23% slower.

## Virtual fly (1 s simulated; physics dt = 0.1 ms)

| Configuration | Wall time | Sim s / wall s |
|---|---|---|
| Baseline controller, empty arena (MuJoCo + FlyGym HybridTurningController) | 3.79 s | 0.26 |
| Baseline controller, light arena (compound-eye rendering at 20 Hz) | 4.20 s | 0.24 |
| Neural controller, synthetic network, food arena | 4.06 s | 0.25 |
| Neural controller, FlyWire v783 full brain, food arena | 7.00 s | **0.14** |

**Neural-to-body latency.** The descending command is updated every bridge interval
(1 ms of simulated time) and lags the neural activity that produced it by one interval.
On the full brain, one interval takes about 7 ms of wall time.

## Data and memory

| Measure | Value |
|---|---|
| FlyWire v783 import + validation (raw files present) | 18.1 s |
| Opening a processed dataset (neuron table + memory-mapped CSR) | 0.018 s |
| Synthetic fixture build | 0.10 s |
| Skeleton index build (5.36 GB → 268 M nodes re-chunked) | 52 s (measured once, separately) |
| Peak RSS (import + all of the above) | 4.1 GB |

## Browser

Brain Explorer on FlyWire v783 (139,255 points, 79 labels) in the Claude desktop app's
Chromium 152 pane (canvas 780 × 855 CSS px, DPR 2): **120 fps** while orbiting
(display-capped), JS heap 69 MB. Measured by counting `requestAnimationFrame`
callbacks during 3 s of scripted orbiting. Safari and other GPUs were not measured.

## Reproduce

```bash
make benchmark      # or: uv run python scripts/benchmarks/run_benchmarks.py [--quick] [--brian2-full]
```
