# ADR 0003 — Default v783 connectivity: the Shiu et al. table

* Status: accepted (2026-11-06)

## Context
FlyWire v783 connectivity exists in several forms (Codex thresholded/unthresholded,
Buhmann vs Princeton synapses, Zenodo feather). Shiu et al.'s `Connectivity_783.parquet`
(15.09M pairs, 54.5M synapses, no threshold, signed) is the table the LIF model was built
and tuned on, and it is downloadable without sign-in.

## Decision
`flywire-783-open` uses the Shiu table by default (`--connectivity shiu`); Codex
connections can be imported instead with `--connectivity codex` (aggregated over
neuropils, signed by presynaptic predicted transmitter). The choice is recorded in the
manifest's `filters`.

## Consequences
Default results are comparable with the reference model. The two connectivity sources
are not interchangeable; comparisons across them must say so.
