# Virtual fly: locomotion after neuronal silencing

Neural controller in the food arena, intact vs with a steering descending group silenced (output blocked).

- Experiment ID: `embodied_flywire783_food_dna02l_silencing`
- Dataset: `flywire_fafb_783` (v783)
- Evidence category: **hypothesis**
- Network: full, 139255 neurons
- Trials: 1 x 2000.0 ms, base seed 0

## Readouts

| Condition | Readout | Mean rate (Hz) | SD across trials |
|---|---|---|---|

## Assumptions

- Synaptic weight = predicted-transmitter sign x synapse count x w_syn (w_syn tuned, not measured).
- Transmitter signs: GABA and glutamate inhibitory, all others excitatory.
- Point neurons; no dendritic compartments, gap junctions, neuromodulation or plasticity.
- Uniform 1.8 ms synaptic delay; no spontaneous activity (only stimulated inputs drive the network).

Reproduce with:

```bash
uv run flymind experiment run experiments/embodied_flywire783_food_dna02l_silencing/spec.json
```
