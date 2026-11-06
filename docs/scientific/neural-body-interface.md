# Neural–body interface

The interface between the simulated brain and the simulated body is declared in
`src/flymind/embodiment/bridge.py`. Every element has a provenance label.

```
World (MuJoCo state)
  └─ sensors (body.py)            odour at antennae · eye luminance · obstacle contacts · on food
       └─ SensoryEncoder          rate = clip(gain·(value − baseline), 0, max)  → Poisson input
            └─ LIF brain          real connectivity, simulated dynamics
                 └─ MotorDecoder  smoothed DN rates → descending command [left, right]
                      └─ HybridTurningController (FlyGym)  CPG + rules → 42 leg joint targets
                           └─ MuJoCo physics → new world state
```

## Who produces what

| Element | Origin | Evidence category |
|---|---|---|
| Body geometry, joints, actuators, contacts, adhesion | NeuroMechFly v2 / FlyGym 2.1.1 | published model |
| Physics | MuJoCo 3.16 (authoritative; the browser only renders streamed poses) | — |
| Leg coordination (stepping, gait) | FlyGym `HybridTurningController` (CPG + sensory-feedback rules; Wang-Chen et al. 2024) | **external algorithm, not the connectome** |
| Choice of sensory neurons per sensor | literature (cited per group in `data/manifests/groups/`) | published |
| Sensor → rate encoding (linear, gains) | FlyMind assumption | assumption |
| Neural dynamics | LIF model on the connectome | simulation output |
| Choice of descending neurons per motor role | literature | published |
| DN rate → descending command mapping | FlyMind assumption (saturating, `r/(r + r_half)`) | assumption |
| Odour field | FlyMind analytic model `I = peak / (1 + (d/scale)²)` (FlyGym 2.x has no olfaction) | assumption |

**No scripted drive is added by default** (`tonic_forward = 0`). If the selected
descending neurons are silent, the command is zero and the fly stands still
(`test_zero_neural_output_means_no_walking`). If a preset ever sets a tonic drive, the
session record contains a `scripted_drive_warning`.

## Timing

Neural and physics time steps are both 0.1 ms. Sensors are read and the command is
updated every **bridge interval** (default 1 ms = 10 steps), so the command lags the
activity that produced it by one interval. Vision is rendered at 20 Hz.

## Presets

### `flywire_literature` (FlyWire v783) — evidence: hypothesis

| Sensor / role | Neuron group | Rationale |
|---|---|---|
| attractive odour L/R | `orn_dm1_left/right` (ORN_DM1, 35/33 neurons) | Or42b ORNs; vinegar attraction (Semmelhack & Wang 2009) |
| aversive odour L/R | `orn_da2_left/right` (16/22) | Or56a ORNs; geosmin aversion (Stensmyr et al. 2012) |
| luminance L/R | `r7_left/right` (672/671) | eye-averaged luminance; columns not mapped individually |
| on food | `sugar_grn_shiu` (20) | sugar GRNs of Shiu et al. 2024 |
| forward | `p9_left/right` (DNp09) | P9 drives forward walking (Bidaye et al. 2020) |
| steering | `dna02_left/right` | DNa02 predicts ipsilateral turning (Rayshubskiy et al. 2025) |
| backward | `mdn_left/right` | MDN drives backward walking (Bidaye et al. 2014) |
| monitor only | `mn9` | proboscis motor neurons (feeding) |

Contact/touch is **not mapped** for FlyWire: leg mechanosensory neurons are in the
ventral nerve cord, which FAFB does not contain.

### `synthetic_demo` (synthetic fixture) — evidence: demonstration

Sensory and descending groups of the synthetic network, whose pathways were wired by
hand. Any behaviour is a demonstration of the pipeline, not a finding.

## What the closed loop showed on FlyWire v783

See [docs/evidence/embodied-flywire.md](../evidence/embodied-flywire.md): odour input to
DM1 ORNs drove DNa02 (left) strongly but not P9, so the neural-controlled fly turned in
place instead of approaching the odour source. This is reported as observed.
