# Silencing intervention

Same stimulation with and without silencing a neuron group (synaptic output blocked, as in the reference model; approximates tetanus-toxin silencing).

- Experiment ID: `flywire783_sugar_silencing`
- Dataset: `flywire_fafb_783` (v783)
- Evidence category: **simulation_output**
- Network: full, 139255 neurons
- Trials: 10 x 1000.0 ms, base seed 0

## Readouts

| Condition | Readout | Mean rate (Hz) | SD across trials |
|---|---|---|---|
| intact | mn9 | 53.65 | 4.31 |
| silenced | mn9 | 51.95 | 4.06 |

## Assumptions

- Synaptic weight = predicted-transmitter sign x synapse count x w_syn (w_syn tuned, not measured).
- Transmitter signs: GABA and glutamate inhibitory, all others excitatory.
- Point neurons; no dendritic compartments, gap junctions, neuromodulation or plasticity.
- Uniform 1.8 ms synaptic delay; no spontaneous activity (only stimulated inputs drive the network).

Reproduce with:

```bash
uv run flymind experiment run experiments/flywire783_sugar_silencing/spec.json
```
