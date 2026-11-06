# ADR 0006 — WebSocket streaming with server-side aggregation; string IDs

* Status: accepted (2026-11-06)

## Decision
The simulation loop never blocks on clients: frames go into bounded per-subscriber
deques; sockets aggregate them at a client-chosen interval and truncate spikes. Body poses
stream as the newest frame only. All root IDs are serialised as strings
(`SafeJSONResponse` converts any integer beyond 2⁵³).

## Consequences
Slow browsers drop intermediate frames instead of slowing the simulation; IDs are never
rounded by JavaScript.
