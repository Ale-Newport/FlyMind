# Limitations

A connectome is not a functional brain. FlyMind's results are model outputs under the
assumptions below and must not be read as measured activity or behaviour.

## Neural model

* Point neurons with one shared parameter set; no dendritic integration, compartments,
  gap junctions, neuromodulation, plasticity, adaptation, spontaneous activity or
  internal state.
* Synaptic weight ∝ synapse count; sign from a machine-learning transmitter prediction
  (GABA/glutamate inhibitory). Glutamate can be excitatory via other receptors; mixed
  and peptidergic signalling are ignored.
* `w_syn` and the Poisson weight are tuned free parameters.
* Uniform 1.8 ms delay; no axonal conduction delays.
* Only stimulated inputs drive activity; the rest of the brain starts and stays silent.

## Connectome data

* FAFB is one adult female; inter-individual variability is not represented.
* Reconstruction errors and missed synapses propagate into the model.
* Neurons outside the proofread set, and 616 v783 neurons absent from the Shiu table,
  have no connections in the default connectivity source.
* No ventral nerve cord: descending neurons have no downstream motor circuit.
* Neuropil assignment uses output synapses only; neuropil meshes are not shown (no
  openly licensed FlyWire per-neuropil meshes were found; labels sit at neuron-position
  medians).

## Embodiment

* Leg coordination is produced by FlyGym's CPG/rule controller, not the connectome.
* Sensor encodings and the DN readout mapping are FlyMind assumptions.
* The odour field is static and analytic (no plume dynamics, no wind).
* Vision uses eye-averaged luminance into R7 neurons; individual ommatidia/columns are
  not mapped; FlyVis is not integrated (requires Python < 3.13).
* Touch is not mapped for FlyWire (no VNC); wings, proboscis and antennae are passive.
* Full-brain closed loop runs at ~0.1–0.2× real time on a laptop CPU.

## Software

* CPU only (no GPU backend is validated); the optional PyTorch extra is not used by
  the engines.
* Sessions are held in memory; the API has no authentication and binds to localhost.
* Safari compatibility was not tested (Chromium only in automated tests).
