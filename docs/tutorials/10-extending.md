# 10. Extending FlyMind

* **New dataset**: subclass `DatasetAdapter` (`connectome/adapters/base.py`), add header
  roles in `detect.py`, produce the canonical tables, add expected statistics to
  `validate.py`, and add dataset-specific tests before switching `status` to `supported`.
* **New neuron groups**: add entries to `data/manifests/groups/<dataset>.json` with a
  description, source and evidence category.
* **New experiment template**: a function returning an `ExperimentSpec` in
  `experiments/templates.py`, registered in `TEMPLATES`.
* **New bridge**: a `BridgeConfig` in `embodiment/bridge.py` (sensor → group, gains,
  motor roles). Keep `tonic_forward = 0` unless you intend scripted drive.
* **New engine**: implement the `advance_*` kernel contract in `brain/kernels.py` and add
  it to `test_numba_and_numpy_backends_identical` and the Brian2 equivalence tests.
