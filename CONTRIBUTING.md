# Contributing to FlyMind

Thanks for helping! FlyMind is a scientific tool, so correctness and transparency come first.

## Set up

```bash
make setup && make test && make test-web
```

## Ground rules

1. **Never present simulation output as measurement.** Label results with the evidence
   categories (`published`, `reproduced`, `simulation_output`, `hypothesis`,
   `demonstration`) and keep model assumptions explicit.
2. **No scripted behaviour disguised as neural output.** Anything that is not the
   connectome model (controllers, encodings, tonic drives) must be named in the bridge
   and the session record.
3. **Never commit FlyWire-derived data** or other datasets whose licence does not allow
   it. Tests use the synthetic fixture; full-data tests are marked `fulldata`.
4. **Identifiers stay int64 in Python and strings in JSON.**
5. **Tests with every change**: unit tests for logic, equivalence tests for engine
   changes (`tests/unit/test_brian2_equivalence.py`), Playwright tests for UI workflows.
6. Keep the layering (`tests/unit/test_architecture.py`) and run `make lint`.

## Pull requests

Describe the scientific motivation, the evidence (test output, benchmark, screenshot
from the running app) and any new assumption. Update `CHANGELOG.md` and the relevant docs.
