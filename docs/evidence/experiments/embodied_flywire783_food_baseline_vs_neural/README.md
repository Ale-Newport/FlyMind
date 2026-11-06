# Virtual fly: baseline vs neural controller (food arena)

Same arena and seed; the baseline condition walks with a fixed descending command (no neural model), the neural condition derives the command from descending-neuron activity driven by odour input.

- Experiment ID: `embodied_flywire783_food_baseline_vs_neural`
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
- Leg kinematics come from FlyGym's HybridTurningController, not from the connectome.
- Odour field is an analytic FlyMind model.

Reproduce with:

```bash
uv run flymind experiment run experiments/embodied_flywire783_food_baseline_vs_neural/spec.json
```
