#!/usr/bin/env bash
# Isolated API for browser tests: fresh data root with only the synthetic fixture.
set -euo pipefail
cd "$(dirname "$0")/../.."
PORT="${1:-8010}"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/flymind-e2e.XXXXXX")"  # portable (GNU and BSD mktemp)
export FLYMIND_DATA_DIR="$ROOT/data" FLYMIND_EXPERIMENTS_DIR="$ROOT/experiments" FLYMIND_LOG_JSON=0
mkdir -p "$FLYMIND_DATA_DIR/processed" "$FLYMIND_EXPERIMENTS_DIR"
uv run flymind data fixture
exec uv run flymind serve --port "$PORT"
