# ADR 0005 — FlyGym's HybridTurningController as the motor layer

* Status: accepted (2026-11-06)

## Context
FAFB contains no ventral nerve cord, so leg motor circuits are not in the connectome.
A body still needs joint-level commands.

## Decision
Use FlyGym 2.1.1's `HybridTurningController` (CPG + sensory-feedback rules) driven by a
two-value descending command. The baseline controller sets the command directly; the
neural controller derives it from smoothed rates of literature-defined descending
neurons. The boundary is explicit in the UI and in every session record.

## Consequences
Leg coordination is never attributed to the connectome. A future BANC/MANC adapter can
replace the controller with VNC circuits behind the same bridge interface.
