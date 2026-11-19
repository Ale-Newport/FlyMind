# Contributing to FlyMind

Thanks for helping! FlyMind is a scientific tool, so correctness and transparency come
first. Questions are welcome in [Discussions](https://github.com/Ale-Newport/FlyMind/discussions);
bugs and proposals go in [issues](https://github.com/Ale-Newport/FlyMind/issues/new/choose).

New here? Look for issues labelled
[`good first issue`](https://github.com/Ale-Newport/FlyMind/labels/good%20first%20issue) or
[`help wanted`](https://github.com/Ale-Newport/FlyMind/labels/help%20wanted). Comment on the
issue before you start so work is not duplicated.

## Set up

You need [uv](https://docs.astral.sh/uv/), Node.js ≥ 20 and a C++ compiler.

```bash
git clone https://github.com/<you>/FlyMind.git && cd FlyMind   # your fork
make setup                      # Python 3.13, locked deps, web deps, synthetic dataset
make test && make test-web      # fast Python tests, type check + Vitest
make dev                        # API on :8000 + web app on :5173
```

`make test-all` adds the MuJoCo and Brian2 tests; `make e2e` runs Playwright. Nothing
needs credentials or downloads: tests run on a small synthetic network.

Optional local hooks (secret scanning with gitleaks, ruff, basic hygiene):

```bash
uvx pre-commit install
```

## How changes get in

1. Fork the repository and create a branch from `main`.
2. Make your change with tests, then open a pull request against `main`.
3. CI must pass: lint, Python tests on Linux and macOS, web type check, unit and
   Playwright tests, docs build, CodeQL, dependency review and secret scanning.
4. Every pull request needs an approving review from the maintainer
   ([CODEOWNERS](.github/CODEOWNERS)). New commits dismiss earlier approvals, and all
   review threads must be resolved before merging.

Workflows on pull requests from first-time contributors run after the maintainer
approves them. Branches in this repository are protected; please do not ask for write
access. Forks are the way to contribute.

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
7. **Never commit secrets.** Configuration goes in `.env` (see `.env.example`), which is
   ignored by git.

## Pull request description

Describe the scientific motivation, the evidence (test output, benchmark, screenshot
from the running app) and any new assumption. Update `CHANGELOG.md` under *Unreleased*
and the relevant docs. The pull request template has a checklist.

## Code style

* Python: ruff (`make format`), type hints, docstrings that say what is a model
  assumption. Line length 100.
* TypeScript: strict mode; keep components small and accessible (labels on controls,
  keyboard operation, visible focus).
* Commits: short imperative subject line ("Add BANC adapter validation"), body
  explaining why.

## Releases

The maintainer tags `vX.Y.Z` on `main`; the release workflow publishes the GitHub
Release with notes from `CHANGELOG.md` and the Python sdist/wheel attached.
