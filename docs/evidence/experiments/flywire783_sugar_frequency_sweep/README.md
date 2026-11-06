# Population stimulation frequency sweep

Sugar-sensing GRNs driven at increasing Poisson rates (cf. Shiu et al. 2024 Fig. 1d); readout of the feeding motor neuron MN9.

- Experiment ID: `flywire783_sugar_frequency_sweep`
- Dataset: `flywire_fafb_783` (v783)
- Evidence category: **simulation_output**
- Network: full, 139255 neurons
- Trials: 5 x 1000.0 ms, base seed 0

## Readouts

| Condition | Readout | Mean rate (Hz) | SD across trials |
|---|---|---|---|
| 25 Hz | mn9 | 0.00 | 0.00 |
| 50 Hz | mn9 | 14.60 | 4.99 |
| 100 Hz | mn9 | 52.70 | 2.11 |
| 150 Hz | mn9 | 66.10 | 2.27 |
| 200 Hz | mn9 | 76.00 | 3.86 |

## Assumptions

- Synaptic weight = predicted-transmitter sign x synapse count x w_syn (w_syn tuned, not measured).
- Transmitter signs: GABA and glutamate inhibitory, all others excitatory.
- Point neurons; no dendritic compartments, gap junctions, neuromodulation or plasticity.
- Uniform 1.8 ms synaptic delay; no spontaneous activity (only stimulated inputs drive the network).

Reproduce with:

```bash
uv run flymind experiment run experiments/flywire783_sugar_frequency_sweep/spec.json
```
