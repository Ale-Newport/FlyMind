# 6. Activating and silencing neurons

* From the Explorer, select a neuron and press **Stimulate in simulator**, **Silence** or
  **Record trace**; the action is applied to the current session of that dataset.
* In the Simulator, *Silencing & perturbation* offers: block synaptic output (≈ tetanus
  toxin; the reference model's method), clamp at rest (≈ Kir2.1), and reversible scaling
  of outgoing connections (factor 0 = lesion; optional target restriction).
* **Restore original connectome** removes all interventions; the stored graph is never
  modified.

Reproducible version: **Experiments → Inhibitory / silencing intervention** runs intact vs
silenced conditions with identical random inputs (common random numbers) and reports
readouts, per-neuron changes and a comparison.
