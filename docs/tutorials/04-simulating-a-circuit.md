# 4. Simulating a small circuit

In **Brain Simulator**:

1. Mode **circuit**, selection **Group → sugar_grn_shiu**, expand 2 hops → *Create session*
   (≈1,500 neurons: the GRNs and their 2-hop downstream neighbourhood with ≥5 synapses).
2. Stimulation: group `sugar_grn_shiu`, Poisson 150 Hz, 0–1000 ms → *Add stimulus*.
3. *Start*. Watch the raster, population rate and regional activity. *Pause*, then *Step*
   in units of dt, or drag the raster window to scrub recorded activity.
4. Click a raster point or use "Trace" in the activity table to record a neuron's membrane
   potential.

Command line equivalent:

```bash
uv run flymind sim run --dataset flywire_fafb_783 --group sugar_grn_shiu --rate 150
```

Circuit mode simulates only the induced subnetwork: inputs from outside it are absent, so
results differ from full-brain mode.
