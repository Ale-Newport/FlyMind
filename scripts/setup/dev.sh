#!/usr/bin/env bash
# Start the FlyMind API and the web dev server together; stop both on Ctrl-C.
set -euo pipefail
cd "$(dirname "$0")/../.."
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
for p in "$API_PORT" "$WEB_PORT"; do
  if port_busy "$p"; then
    echo "Port $p is already in use. Stop the other process or run e.g. 'make dev API_PORT=8010 WEB_PORT=5174'." >&2
    exit 1
  fi
done
[ -d .venv ] || { echo "Python environment missing: run 'make setup' first." >&2; exit 1; }
[ -d apps/web/node_modules ] || { echo "Web dependencies missing: run 'make setup' first." >&2; exit 1; }
if ! uv run flymind data info | grep -q synthetic_demo_v1; then
  echo "Building the synthetic demonstration dataset..."
  uv run flymind data fixture
fi

pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

FLYMIND_LOG_JSON=0 uv run flymind serve --port "$API_PORT" &
pids+=($!)
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1; then break; fi
  if ! kill -0 "${pids[0]}" 2>/dev/null; then echo "API failed to start (see output above)." >&2; exit 1; fi
  sleep 0.5
done
(cd apps/web && FLYMIND_API="http://127.0.0.1:$API_PORT" npx vite --host 127.0.0.1 --port "$WEB_PORT" --strictPort) &
pids+=($!)
sleep 2
echo ""
echo "  FlyMind is running:  http://127.0.0.1:$WEB_PORT${OPEN_PATH:-/}"
echo "  API docs:            http://127.0.0.1:$API_PORT/docs"
echo "  Press Ctrl-C to stop."
# Portable "wait for the first child to exit" (macOS ships bash 3.2 without `wait -n`).
while kill -0 "${pids[0]}" 2>/dev/null && kill -0 "${pids[1]}" 2>/dev/null; do sleep 1; done
echo "A server stopped; shutting down." >&2
