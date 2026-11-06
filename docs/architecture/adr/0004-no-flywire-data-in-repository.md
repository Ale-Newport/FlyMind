# ADR 0004 — Never commit FlyWire-derived data

* Status: accepted (2026-11-06)

## Context
flywire.ai/guidelines states CC BY-NC 4.0 for the public release; the Zenodo deposits
say CC BY 4.0; the annotation repository has no licence file. FlyMind's code is MIT.

## Decision
No FlyWire-derived file is committed (`data/raw`, `data/processed`, `data/cache` are
git-ignored). Users fetch pinned, checksummed files themselves. Tests and the public demo
use a generated synthetic fixture; curated neuron *IDs* (group files) are committed as
references to published identifiers.

## Consequences
Fresh clones run without credentials or large downloads; real-data features require one
command. Licence obligations stay with the data provider's terms.
