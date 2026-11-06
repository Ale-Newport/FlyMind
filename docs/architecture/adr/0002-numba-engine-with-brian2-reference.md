# ADR 0002 — Numba event-driven engine, Brian2 as the validation reference

* Status: accepted (2026-11-06)

## Context
Brian2 is the reference simulator of Shiu et al. (2024) but rebuilds and recompiles
networks per run and is awkward to pause, step and modify interactively. Interactive
full-brain use needs fast stepping, live interventions and chunking.

## Decision
The default engine is a Numba kernel with Brian2's exact semantics (operation order,
`(unless refractory)` conditional writes, refractory window, delays, exact linear
integration). A Brian2 build of the reference equations runs on identical pre-generated
input events and is used in tests and benchmarks.

## Consequences
Spike-for-spike equivalence is tested on the fixture; the published v630 sugar→MN9 rates
are reproduced. Brian2 remains a dependency (validation, optional use).
