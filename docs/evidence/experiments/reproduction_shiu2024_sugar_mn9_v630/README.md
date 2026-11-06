# Sugar GRN -> MN9 (reproduction of Shiu et al. 2024)

Exact v630 network and neuron IDs of the reference example: 21 sugar GRNs Poisson-driven at 200 Hz and 100 Hz, 30 trials of 1 s; MN9 firing rate compared with the reference implementation's committed results.

- Experiment ID: `reproduction_shiu2024_sugar_mn9_v630`
- Dataset: `flywire_fafb_630_shiu` (v630)
- Evidence category: **reproduced**
- Network: full, 127400 neurons
- Trials: 30 x 1000.0 ms, base seed 0

## Readouts

| Condition | Readout | Mean rate (Hz) | SD across trials |
|---|---|---|---|
| 200 Hz | mn9_shiu | 93.40 | 4.83 |
| 100 Hz | mn9_shiu | 67.60 | 4.91 |

## Comparison with reference values

| Readout | Condition | Reference (Hz) | Observed (Hz) | Tolerance | Status | Source |
|---|---|---|---|---|---|---|
| mn9_shiu | 200 Hz | 93.3 | 93.40 | +-3.0 | pass | Shiu et al. 2024 reference results (results/example/sugarR*.parquet in philshiu/Drosophila_brain_model @91bdd1e7; mean of 30 trials, v630) |
| mn9_shiu | 100 Hz | 67.0 | 67.60 | +-4.0 | pass | Shiu et al. 2024 reference results (results/example/sugarR*.parquet in philshiu/Drosophila_brain_model @91bdd1e7; mean of 30 trials, v630) |

## Assumptions

- Synaptic weight = predicted-transmitter sign x synapse count x w_syn (w_syn tuned, not measured).
- Transmitter signs: GABA and glutamate inhibitory, all others excitatory.
- Point neurons; no dendritic compartments, gap junctions, neuromodulation or plasticity.
- Uniform 1.8 ms synaptic delay; no spontaneous activity (only stimulated inputs drive the network).

Reproduce with:

```bash
uv run flymind experiment run experiments/reproduction_shiu2024_sugar_mn9_v630/spec.json
```
