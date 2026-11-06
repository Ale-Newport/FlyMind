# Reproduction: Shiu et al. 2024, sugar GRN → MN9

**Evidence category: reproduced.** The published reference values were re-obtained by
running FlyMind.

## Original experiment

Shiu et al. (2024) activated 21 labellar sugar-sensing gustatory receptor neurons
("sugarR") with Poisson input in a whole-brain LIF model of the FlyWire v630 connectome.
They read out the proboscis motor neuron MN9 (`720575940660219265`), which mediates
feeding initiation in flies. Their repository commits the spike output of this example
(`results/example/sugarR.parquet`, 200 Hz, and `sugarR_100Hz.parquet`, 30 trials × 1 s
each). Its mean MN9 rate is **93.3 ± 3.2 Hz** at 200 Hz and **67.0 ± 6.6 Hz** at 100 Hz
(mean ± SD across trials, `get_rate` convention, our re-analysis of the committed files).

## How FlyMind approximates it

| Aspect | Reference | FlyMind |
|---|---|---|
| Network | v630 completeness/connectivity files | the same files (SHA-256 pinned), imported as `flywire_fafb_630_shiu` |
| Neurons stimulated | 21 sugar GRN IDs from `example.ipynb` | the same 21 IDs (`data/manifests/groups/flywire_fafb_630_shiu.json`) |
| Model | Brian2, `method='linear'`, dt 0.1 ms | FlyMind Numba engine with Brian2 semantics (spike-identical on test networks) |
| Input | `PoissonInput` (Brian2 RNG, unseeded) | pre-generated Bernoulli(rate·dt) input spikes, seeds 0–29 |
| Trials | 30 × 1 s, independent | 30 × 1 s, seeds 0–29 (common to both conditions) |

## Result

Commit `a4e2bcd`; total wall time 128 s (≈2.1 s per 1 s trial of the 127,400-neuron
network).

| Condition | MN9 mean (Hz) | SD across trials | Reference mean | Tolerance | Status |
|---|---|---|---|---|---|
| 200 Hz | **93.40** | 4.83 | 93.3 | ±3.0 | pass |
| 100 Hz | **67.60** | 4.91 | 67.0 | ±4.0 | pass |

Secondary statistics at 200 Hz: 17,015 spikes per trial (reference ≈ 17,052) and 456
neurons active in at least one trial (reference: 448).

## Differences and open points

* The means agree to within 0.1 Hz and 0.6 Hz. The **trial-to-trial SDs differ** (4.8 vs
  3.2 Hz at 200 Hz; 4.9 vs 6.6 Hz at 100 Hz). With 30 trials an SD estimate has roughly
  ±26 % sampling uncertainty, which does not fully explain the 200 Hz difference. This
  was not investigated further and is recorded as an open point.
* The random input streams necessarily differ, because the reference sets no seed.
  Agreement is therefore statistical, not spike-for-spike.

## Reproduce

```bash
make data-630
uv run flymind experiment run sensory_circuit --dataset flywire_fafb_630_shiu
```

Raw record: [`experiments/reproduction_shiu2024_sugar_mn9_v630/record.json`](experiments/reproduction_shiu2024_sugar_mn9_v630/record.json).
