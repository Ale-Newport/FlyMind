# FlyMind developer commands. Run `make help` for the list.
SHELL := /bin/bash
UV ?= uv
NPM ?= npm
API_PORT ?= 8000
WEB_PORT ?= 5173
WEB := apps/web

.DEFAULT_GOAL := help
.PHONY: help setup setup-python setup-web fixture dev api web explorer brain virtual-fly \
        data-flywire data-630 data-skeletons reproduce test test-all test-fulldata test-web e2e \
        lint format benchmark docs docs-serve build-web pages-build doctor clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: setup-python setup-web fixture ## Install everything and build the synthetic demo dataset
	@echo "Setup complete. Next: make dev"

setup-python: ## Install Python 3.13 + dependencies with uv (from uv.lock)
	@command -v $(UV) >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
	$(UV) python install 3.13
	$(UV) sync --frozen

setup-web: ## Install web dependencies (from package-lock.json)
	@command -v node >/dev/null || { echo "Node.js >= 20 is required: https://nodejs.org/"; exit 1; }
	cd $(WEB) && $(NPM) ci

fixture: ## Build the small SYNTHETIC demonstration dataset (no download)
	$(UV) run flymind data fixture

dev: ## Start API (http://127.0.0.1:$(API_PORT)) and web app (http://127.0.0.1:$(WEB_PORT))
	@API_PORT=$(API_PORT) WEB_PORT=$(WEB_PORT) bash scripts/setup/dev.sh

api: ## Start only the API
	$(UV) run flymind serve --port $(API_PORT)

web: ## Start only the web dev server (expects the API on $(API_PORT))
	cd $(WEB) && FLYMIND_API=http://127.0.0.1:$(API_PORT) $(NPM) run dev

explorer: ## Start everything and open the Brain Explorer
	@OPEN_PATH="/#/explorer" API_PORT=$(API_PORT) WEB_PORT=$(WEB_PORT) bash scripts/setup/dev.sh

brain: ## Headless brain simulation demo (synthetic fixture)
	$(UV) run flymind sim run --dataset synthetic_demo_v1 --group grn_sugar --rate 150 --duration-ms 1000

virtual-fly: ## Headless virtual-fly demo (baseline controller, empty arena)
	$(UV) run flymind fly run --arena empty --controller baseline --duration-s 2

data-flywire: ## Download + import + validate FlyWire v783 (open sources, ~150 MB)
	$(UV) run flymind data fetch flywire-783

data-630: ## Download + import the Shiu et al. v630 network (reproduction only, ~90 MB)
	$(UV) run flymind data fetch flywire-630

data-skeletons: ## Download + index FlyWire v783 skeletons (5.4 GB, optional)
	$(UV) run flymind data fetch skeletons

reproduce: ## Reproduce Shiu et al. 2024 sugar->MN9 on v630 (needs data-630; ~2 min)
	$(UV) run flymind experiment run sensory_circuit --dataset flywire_fafb_630_shiu

test: ## Fast test suite (fixtures only; no downloads)
	$(UV) run pytest -m "not fulldata and not physics and not brian2"

test-all: ## All tests that do not need downloaded data (includes MuJoCo and Brian2)
	$(UV) run pytest -m "not fulldata"

test-fulldata: ## Tests on the real FlyWire datasets (skipped if not installed)
	$(UV) run pytest -m fulldata

test-web: ## Frontend unit tests (Vitest) and type check
	cd $(WEB) && npx tsc -b && $(NPM) test

e2e: ## Browser end-to-end tests (Playwright, Chromium); starts the servers itself
	cd $(WEB) && npx playwright test

lint: ## Ruff + TypeScript checks
	$(UV) run ruff check src tests scripts
	cd $(WEB) && npx tsc -b

format: ## Auto-format Python
	$(UV) run ruff check --fix src tests scripts
	$(UV) run ruff format src tests scripts

benchmark: ## Run and record performance benchmarks (docs/evidence/benchmarks)
	$(UV) run python scripts/benchmarks/run_benchmarks.py

docs: ## Build the MkDocs site into site/
	$(UV) run --group docs mkdocs build --strict

docs-serve: ## Serve the documentation locally
	$(UV) run --group docs mkdocs serve -a 127.0.0.1:8001

build-web: ## Production build of the web app (served by `flymind serve`)
	cd $(WEB) && $(NPM) run build

pages-build: ## Static GitHub Pages build (synthetic demo, no backend)
	$(UV) run python scripts/data/export_static_demo.py
	cd $(WEB) && $(NPM) run build:pages

doctor: ## Diagnose the local environment
	$(UV) run flymind doctor

clean: ## Remove build artefacts (keeps datasets)
	rm -rf $(WEB)/dist site .pytest_cache .ruff_cache
