# Propagation across regions

A 200 ms olfactory receptor neuron stimulus; activity spreads across neuropils (see regions.csv and timecourse.csv).

- Experiment ID: `flywire783_dm1_propagation`
- Dataset: `flywire_fafb_783` (v783)
- Evidence category: **simulation_output**
- Network: full, 139255 neurons
- Trials: 5 x 500.0 ms, base seed 0

## Readouts

| Condition | Readout | Mean rate (Hz) | SD across trials |
|---|---|---|---|
| odor pulse | orn_dm1_left | 59.39 | 1.46 |
| odor pulse | p9_left | 0.00 | 0.00 |
| odor pulse | dna02_left | 40.40 | 3.44 |
| odor pulse | dna02_right | 0.00 | 0.00 |

## Assumptions

- Synaptic weight = predicted-transmitter sign x synapse count x w_syn (w_syn tuned, not measured).
- Transmitter signs: GABA and glutamate inhibitory, all others excitatory.
- Point neurons; no dendritic compartments, gap junctions, neuromodulation or plasticity.
- Uniform 1.8 ms synaptic delay; no spontaneous activity (only stimulated inputs drive the network).

Reproduce with:

```bash
uv run flymind experiment run experiments/flywire783_dm1_propagation/spec.json
```
