# ADR 0007 — FlyVis not integrated in this release

* Status: accepted (2026-11-06)

## Context
FlyVis 1.2.0 requires Python < 3.13; Brian2 2.11 (used for validation) requires
Python ≥ 3.13. FlyVis is trained on FIB25/FIB19, not FlyWire.

## Decision
Vision uses FlyGym's ommatidia readouts (eye-averaged luminance → R7 groups). The
integration path (export weights, port the FlyGym v1 `RetinaMapper`, whose ommatidia map is
identical in FlyGym 2.1.1) is documented for future work.
