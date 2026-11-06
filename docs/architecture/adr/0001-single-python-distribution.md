# ADR 0001 — One Python distribution with layered subpackages

* Status: accepted (2026-11-06)

## Context
The brief suggests `packages/{connectome,brain,embodiment,...}` and `services/api` as
separate directories. The three products must share one dataset representation and one
simulation infrastructure.

## Decision
A single installable package `flymind` (`src/flymind/`) with subpackages `common`,
`connectome`, `brain`, `visualization`, `embodiment`, `experiments`, `api`, plus the CLI.
Layering is enforced by `tests/unit/test_architecture.py`. The web app lives in
`apps/web`.

## Consequences
One `uv.lock`, one version, no inter-package release choreography; module boundaries are
still explicit and tested. Splitting into separate distributions later is mechanical.
