# Reference repositories

Inspection date: **2026-11-06**. All repositories were shallow-cloned and read; no code
from them was executed (FlyGym was installed from PyPI as a dependency and run through
its public API). Commit SHAs are the `HEAD` of the default branch on that date.

## Comparison matrix

| Repository | Inspected commit (date) | Scientific purpose | Implemented capabilities | Languages / frameworks | Datasets | Key dependencies | License | Maintenance | Use in FlyMind |
|---|---|---|---|---|---|---|---|---|---|
| [philshiu/Drosophila_brain_model](https://github.com/philshiu/Drosophila_brain_model) | `91bdd1e7` (2024-09-14) | Whole-brain LIF model of Shiu et al. 2024 (Nature 634:210) | Brian2 LIF, Poisson activation, output silencing, rate analysis, notebooks for all figures | Python 3.10, Brian2 2.5.1 | FlyWire v630 (figures) and v783 (`Completeness_783.csv`, `Connectivity_783.parquet`) | brian2, pandas, joblib, pyarrow | MIT | Frozen reference code; no tests/CI | **Model reimplemented** from its equations/parameters (facts, MIT); its v630/v783 data files are **fetched at a pinned commit** with SHA-256 checks; its committed results are the **reproduction target** |
| [eonsystemspbc/fly-brain](https://github.com/eonsystemspbc/fly-brain) | `a3db62f9` (2026-08-29) | Multi-backend benchmark/port of the Shiu model | Brian2 C++/CUDA, PyTorch, NEST GPU, GeNN; cross-simulator parity scripts; benchmark grid | Python, CUDA | Same v783 files as Shiu (byte-identical) | brian2cuda, torch, GeNN | **GPL-2.0-or-later** | Active (2026-08) | **Consulted only** (GPL; no code copied). Informed the equivalence-testing approach (spike/rate parity metrics) |
| [Lulzx/fly-brain](https://github.com/Lulzx/fly-brain) | `ba0b4f81` (2026-10-05) | Browser-based embodied whole-CNS connectome | JS/WASM/WebGPU LIF, MuJoCo-WASM flybody, flyvis vision, compact binary codecs, "scaffold ledger" | JavaScript, C→WASM, WGSL, three.js | Male CNS v1.0 (not FlyWire) | @mujoco/mujoco, flyvis weights | MIT (code); bundled data under own licences | Very young, single author, no CI tests | **Consulted** for honesty practices: its own ledger shows walking needs hand-written CPG/scheduler scaffolds (0.0083 cm graph-only vs 29.77 cm with scaffolds). FlyMind adopts the principle of naming every non-connectome mechanism and offering a baseline |
| [FlyBrainLab/FlyBrainLab](https://github.com/FlyBrainLab/FlyBrainLab) | `5dd079af` (2025-09-28) | Interactive circuit exploration and executable circuits | JupyterLab 3 extension (Neu3D, NeuGFX), NeuroArch DB, Neurokernel GPU execution | Python ≤3.10, TypeScript, OrientDB, PyCUDA | FlyCircuit, Hemibrain, MANC, FlyWire 630/783 dumps | JupyterLab <3.6, CUDA, MPI | BSD-3-Clause | Dormant (no commits in 12 months) | **Consulted** for UI concepts (linked 3D/info/circuit panes, query → simulate workflow) |
| [TuragaLab/flyvis](https://github.com/TuragaLab/flyvis) | `0a69fa2f` (2026-10-13) | Connectome-constrained visual system model (Lappalainen et al. 2024) | 45,669-cell graded network on a 721-column hex lattice; 50 pretrained models | Python, PyTorch | FIB25/FIB19 optic-lobe connectome (not FlyWire) | torch, hydra, datamate | MIT | Active (v1.2.0) | **Not integrated**: `requires-python <3.13` is incompatible with FlyMind's Python 3.13 (required by Brian2 2.11). Integration path documented (export weights; reuse FlyGym v1 `RetinaMapper`, whose ommatidia map is identical in FlyGym 2.1.1) |
| [navis-org/navis](https://github.com/navis-org/navis) | `889caf80` (2026-11-03) | Neuron morphology analysis | SWC/mesh/precomputed I/O, transforms, NBLAST, plotting | Python (+Rust core in 2.0) | Any | trimesh, igraph, navis-fastcore | **GPL-3.0-or-later** | Very active | **Optional extra only** (`uv sync --extra anatomy`); FlyMind's runtime parses skeletons itself and never vendors GPL code |
| [navis-org/navis-flybrains](https://github.com/navis-org/navis-flybrains) | `789e416b` (2026-10-21) | Template brains, meshes, transforms | FAFB14/FLYWIRE outline meshes, bridging transforms | Python data package | 31 templates | navis | GPL-3.0-or-later | Active | **Consulted**: provides no per-neuropil FlyWire meshes; FlyMind labels neuropils at neuron-position medians instead |
| [kornel77777/fly-brain-sim](https://github.com/kornel77777/fly-brain-sim) | `7a05be70` (2026-09-29) | v783 3D viewer + Numba LIF | Header-detected Codex import, BIGINT ID discipline, CSR event-driven LIF, FastAPI | Python 3.12, React, three.js | FlyWire v783 (Codex + Shiu files) | duckdb, numba, polars | MIT | Active | **Ideas adapted** (pinned-commit fetching with checksums, float-corruption ID tests, sign-agreement test). Its kernel freezes 22 steps after a spike (Brian2: 21) and accumulates refractory input; FlyMind matches Brian2 instead |
| [vaibhavkedarisetti/fruit-fly-lab](https://github.com/vaibhavkedarisetti/fruit-fly-lab) | `26672e06` (2026-08-28) | Looming-escape demo (LC4/LPLC2 → DNp01) | Kinematic body, Python/JS LIF engines, checksum provenance | Python, JavaScript | Codex v783 `connections_princeton` | numpy, scipy, fastapi | **No license file** (all rights reserved) | Active | **Consulted only** (unlicensed). Uses a different synapse table and step ordering than the reference model |
| [NeLy-EPFL/flygym](https://github.com/NeLy-EPFL/flygym) | `a63dc91a` (2026-10-24), PyPI **2.1.1** | NeuroMechFly v2 body + MuJoCo simulation | 2.x API: `Simulation`, compose API (`NeuroMechFly`, `FlatGroundWorld`), vision (`get_ommatidia_readouts`), contacts, demo controllers (`flygym_demo`: CPG, rule-based, hybrid, `HybridTurningController`) | Python, MuJoCo 3.16 | NeuroMechFly v2 model | mujoco, numba | Apache-2.0 | Active (2.x rewrite, 2026) | **Reused as a dependency** (body, physics, vision, walking controller). 2.x has no olfaction module, so FlyMind adds an analytic odour field |

## Key verified facts used in the implementation

### Shiu et al. reference model (`model.py`)

* Equations (Brian2, `method='linear'`, default dt 0.1 ms):
  `dv/dt = (v_0 - v + g) / t_mbr : volt (unless refractory)`,
  `dg/dt = -g / tau : volt (unless refractory)`; threshold `v > v_th`;
  reset `v = v_rst; w = 0; g = 0 * mV`; refractory `rfc`.
* Parameters: `v_0 = v_rst = -52 mV`, `v_th = -45 mV`, `t_mbr = 20 ms`, `tau = 5 ms`,
  `t_rfc = 2.2 ms`, `t_dly = 1.8 ms`, `w_syn = 0.275 mV` (free parameter),
  `r_poi = 150 Hz`, `f_poi = 250`.
* Synapses: `on_pre='g += w'`, `w = Excitatory x Connectivity x w_syn`, delay 1.8 ms.
* Stimulation: `PoissonInput(target_var='v', N=1, rate=r_poi, weight=w_syn*f_poi)` and
  the stimulated neuron's `rfc` is set to 0 ms.
* Silencing: only *outgoing* synapses are zeroed (the README says "to and from").
* No random seed is set in the reference code; trials are independent re-builds.
* Data: `Completeness_783.csv` (138,639 neurons; unnamed index = root ID);
  `Connectivity_783.parquet` (15,091,983 rows, 54,492,922 synapses, no threshold,
  signs per presynaptic neuron: GABA/glutamate −1, else +1).
* Committed results (`results/example/sugarR*.parquet`, v630, 30 trials): MN9
  (`720575940660219265`) 93.3 ± 3.2 Hz at 200 Hz sugar-GRN drive and 67.0 ± 6.6 Hz at
  100 Hz. (The notebook text says the default is 200 Hz while `model.py` uses 150 Hz;
  the committed parquet is consistent with 200 Hz.)

### Brian2 semantics verified empirically (Brian2 2.11)

`(unless refractory)` is implemented as a **conditional write**: every code object other
than the thresholder/resetter (including `Synapses.on_pre` and `PoissonInput`) skips
writes to that variable while the target is refractory. Synaptic input arriving during
refractoriness is therefore **discarded**, not accumulated. FlyMind's kernel implements
this (`drop_input_during_refractory=True`) and `tests/unit/test_brian2_equivalence.py`
checks spike-for-spike agreement with Brian2.

### FlyWire data access

* Codex downloads (`codex.flywire.ai/api/download`) require Google sign-in and terms
  acceptance; FlyMind never automates them. A public storage bucket behind Codex exists
  but is not the documented user route, so it is not used.
* Open sources fetched automatically: Zenodo 10.5281/zenodo.10676866 (CC BY 4.0;
  `proofread_root_ids_783.npy`, `per_neuron_neuropil_count_pre_783.feather`), Zenodo
  10.5281/zenodo.10877326 (CC BY 4.0; skeletons, opt-in), Shiu et al. files at a pinned
  commit, and `flyconnectome/flywire_annotations` at commit `c294fba4` (last revision
  whose root IDs match v783 exactly; the repository has no licence file).
* Licence: flywire.ai/guidelines states CC BY-NC 4.0 for the public release, while the
  Zenodo deposits are labelled CC BY 4.0. FlyMind therefore does **not** commit or
  redistribute any FlyWire-derived data; tests use a synthetic fixture.
* Annotation-TSV positions are in 4×4×40 nm voxels (converted to nm on import);
  Codex `coordinates.csv` positions are in nm.

### Licensing decisions

* FlyMind original code: **MIT**. Compatible with reused Apache-2.0 (FlyGym, used as a
  dependency) and MIT sources consulted.
* GPL code (Eon, navis, navis-flybrains) is not copied; navis is an optional,
  separately installed extra.
* See `THIRD_PARTY_NOTICES.md` for the full dependency inventory.
