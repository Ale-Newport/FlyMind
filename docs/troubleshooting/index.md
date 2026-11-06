# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Dataset 'flywire_fafb_783' is not installed" | Run `uv run flymind data fetch flywire-783` (or `make data-flywire`). |
| Import refused: "root ids not in the v783 neuron set" | Files from another release/specimen were mixed in. Keep one release per folder. |
| "checksum mismatch" during fetch | The upstream file changed or the download was corrupted; delete `data/raw/<bundle>/<file>` and retry. Report persistent mismatches. |
| Skeleton panel says "not installed" | Optional: `uv run flymind data fetch skeletons` (5.4 GB + ~6 GB index). |
| `ModuleNotFoundError: flymind` | Run commands through `uv run …` (or activate `.venv`). |
| Brian2 compile errors | Install a C++ compiler (`xcode-select --install` / `build-essential`). Tests use `codegen="numpy"` and do not need one. |
| MuJoCo `GLFW`/`gladLoadGL` errors (vision) | Headless Linux: `export MUJOCO_GL=egl` or `osmesa`. macOS needs no setting. |
| Apple Silicon: very slow Python / x86 wheels | Ensure an arm64 Python: `uv run python -c "import platform; print(platform.machine())"` must print `arm64`. `make setup` installs a uv-managed arm64 CPython 3.13. |
| Out of memory | Full-brain sessions need ~1 GB each; the import peaks at ~4 GB. Close sessions (max 6 are kept) or use circuit/region mode. |
| Simulation slower than real time | Expected for the full brain on CPU (≈0.4×). Use region/circuit modes, shorter runs, or `speed` control for viewing. |
| `Port 8000 is already in use` | `make dev API_PORT=8010 WEB_PORT=5174`. |
| Web app shows "backend offline" | Start the API (`make api`) or check the terminal for errors; the web app proxies `/api` and `/ws` to `127.0.0.1:8000`. |
| Dependency conflicts | Use the lockfiles: `uv sync --frozen`, `npm ci`. Do not mix conda environments. |
| Playwright cannot start a browser | `cd apps/web && npx playwright install chromium`. |
