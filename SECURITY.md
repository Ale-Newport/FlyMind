# Security policy

## Supported versions
The latest release on `main`.

## Model
FlyMind is a local research tool. The API **has no authentication** and binds to
`127.0.0.1` by default; do not expose it to untrusted networks (`flymind serve --host`
prints a warning). The API never executes user-supplied code, never reads arbitrary
paths (identifiers are validated and joined with a containment check), serves files only
from a fixed whitelist of experiment artefacts, bounds request sizes, durations and the
number of sessions/jobs, and restricts CORS to local development origins.

Downloads are fetched only from pinned URLs and verified against SHA-256 checksums;
downloaded data is parsed as data (Parquet/CSV/NumPy with `allow_pickle=False`).

## Reporting
Please report vulnerabilities privately via GitHub security advisories on the repository,
not in public issues. Expect an acknowledgement within a week.
