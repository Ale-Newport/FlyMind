# Security policy

## Supported versions

| Version | Supported |
|---|---|
| latest release and `main` | ✅ |
| older releases | ❌ (please upgrade) |

## Reporting a vulnerability

Please report vulnerabilities **privately** through
[GitHub private vulnerability reporting](https://github.com/Ale-Newport/FlyMind/security/advisories/new),
not in public issues or discussions. Include the affected version or commit, steps to
reproduce, and the impact you expect.

You can expect an acknowledgement within 7 days and a fix or mitigation plan within
30 days for confirmed issues. You will be credited in the advisory unless you prefer
otherwise.

## Security model

FlyMind is a **local research tool**. Its API has **no authentication** and is designed
to be reached only from the same machine.

* The API binds to `127.0.0.1` by default; `flymind serve --host` prints a warning for
  any other address.
* **DNS rebinding protection:** requests are accepted only when the `Host` header names
  a loopback host (`localhost`, `127.0.0.1`, `::1`) or a name listed in
  `FLYMIND_ALLOWED_HOSTS`.
* **Cross-site WebSockets are refused:** a WebSocket handshake is rejected unless its
  `Origin` is an allowed CORS origin (`FLYMIND_CORS_ORIGINS`), the API's own origin, or a
  page served from this machine (a loopback host name).
* CORS is restricted to the local development origins.
* Request bodies are capped (`FLYMIND_MAX_BODY_BYTES`, default 4 MiB), list inputs have
  length limits, and simulation durations, time steps, bin counts, live sessions and
  queued jobs are bounded.
* The API never executes user-supplied code and never reads arbitrary paths:
  identifiers are validated and joined with a containment check, and files are served
  only from a fixed whitelist of experiment artefacts.
* Downloads come only from pinned URLs and are verified against SHA-256 checksums;
  downloaded data is parsed as data (Parquet/CSV/NumPy with `allow_pickle=False`).

The public GitHub Pages site is a static, browser-only preview of a synthetic network.
It has no backend and handles no user data.

## Supply chain

* Dependencies are locked (`uv.lock`, `package-lock.json`) and audited in CI
  (`pip-audit`, `npm audit`, GitHub dependency review); Dependabot proposes updates.
* GitHub Actions are pinned to full commit SHAs and run with read-only tokens by
  default; only the Pages deploy and release jobs get write permissions.
* CodeQL, secret scanning with push protection, TruffleHog history scans and the
  OpenSSF Scorecard run on the repository.
