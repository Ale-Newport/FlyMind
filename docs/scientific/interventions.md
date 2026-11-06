# Stimulation and interventions

Interventions never modify the stored connectome. Effective weights are recomputed
from the original synapse counts whenever an intervention is added or removed, and
"Restore original connectome" removes all of them (tested in
`test_silencing_and_reversible_lesions`).

| FlyMind operation | Model implementation | Biological experiment it approximates | Caveats |
|---|---|---|---|
| Poisson stimulation | Bernoulli(rate·dt) input spikes adding 68.75 mV to *v*; target's refractory period set to 0 (reference method) | Optogenetic/thermogenetic activation (CsChrimson, TrpA1) at a chosen firing rate | Imposes a firing rate rather than modelling channel kinetics |
| Pulse train | Input spikes at a fixed frequency | Pulsed light stimulation | Perfectly periodic |
| Current injection | Constant drive *I* (mV, = R·I) added to the membrane equation | Intracellular current injection | FlyMind extension; one R for all neurons |
| Silencing: `block_output` | Outgoing weights of the targets set to 0 (reference method); targets still spike | Tetanus-toxin light chain (blocks release) | Spikes of blocked descending neurons are also excluded from the virtual-fly motor readout |
| Silencing: `clamp` | Membrane held at rest; no spikes | Kir2.1 hyperpolarisation | Instantaneous and complete |
| Synaptic scaling | Selected pre→(post) weights multiplied by a factor (0 = lesion) | Connection-specific lesion or modulation | Reversible; not a model of plasticity |
| Repeated stimuli | Any stimulus with `repeats` and `interval_ms` | Repeated trials within one preparation | The model has no adaptation or plasticity |

Note on the reference model: its README describes silencing as removing connections
"to and from" the neurons, but its code (`model.py`, `silence()`) zeroes only the
**outgoing** synapses. FlyMind follows the code.
