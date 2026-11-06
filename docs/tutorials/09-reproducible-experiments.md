# 9. Running a reproducible experiment

Every run writes `experiments/<id>/` with `spec.json` (complete inputs), `record.json`
(dataset files and checksums, seeds, software versions, git commit, machine, timing,
resolved neuron IDs, assumptions, evidence category), `spikes.parquet`, `rates.parquet`,
`readouts.csv`, `timecourse.csv`, `regions.csv` and a `README.md`.

```bash
make data-630
uv run flymind experiment run sensory_circuit --dataset flywire_fafb_630_shiu
# re-run exactly from the saved spec:
uv run flymind experiment run experiments/<id>/spec.json
uv run flymind experiment compare <id_a> <id_b>
```

Plot a saved result: `uv run python scripts/validation/plot_experiment.py experiments/<id>`.
