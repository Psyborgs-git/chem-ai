# Chemistry Studio — implementation command contract (handoff §26.1).
# Cross-platform note: where Make is unavailable, run the equivalent
# commands documented after each target. No target prints success for
# skipped checks — missing prerequisites exit non-zero with a reason.

SHELL := /bin/bash
UV ?= uv
PNPM ?= pnpm
PYTEST := $(UV) run --group dev pytest
ALEMBIC := $(UV) run alembic
COMPOSE := docker compose -f infra/local/compose.yaml
PACK := docs/chemistry-studio

.DEFAULT_GOAL := help

.PHONY: help
help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  make %-18s %s\n", $$1, $$2}'

## ---------- setup ----------

.PHONY: bootstrap
bootstrap: ## Install locked deps (core profile only; no models, no licenses)
	$(UV) sync --python 3.12 --group dev --frozen
	$(PNPM) install --frozen-lockfile
	@echo "bootstrap complete: core profile only. Optional profiles:"
	@echo "  uv sync --extra engines|local_ai|optimization|quantum|training"
	@echo "Bootstrap never downloads models or accepts licenses (AT-0002-2)."

.PHONY: dev
dev: ## Start postgres + API (loopback) + web dev server
	$(COMPOSE) up -d postgres
	$(UV) run --group dev uvicorn studio.api.app:create_app \
	  --factory --host 127.0.0.1 --port 8787 --reload & \
	$(PNPM) --filter studio-web dev

.PHONY: db-up
db-up: ## Start local postgres container
	@if (echo > /dev/tcp/127.0.0.1/54329) 2>/dev/null; then \
	  echo "postgres already listening on 127.0.0.1:54329 — reusing"; \
	else \
	  $(COMPOSE) up -d postgres; \
	fi

.PHONY: db-down
db-down: ## Stop local postgres container
	$(COMPOSE) down

.PHONY: migrate
migrate: ## Apply database migrations
	$(ALEMBIC) -c services/studio-api/migrations/alembic.ini upgrade head

.PHONY: seed-demo
seed-demo: ## Load SYNTHETIC demo data (labels visible, non-scientific)
	@if [ -f fixtures/synthetic/load_demo.py ]; then \
	  $(UV) run python fixtures/synthetic/load_demo.py; \
	else \
	  echo "BLOCKED: demo loader requires domain schema (P02); no result claimed"; \
	  exit 2; \
	fi

## ---------- checks ----------

.PHONY: lint
lint: ## ruff lint
	$(UV) run --group dev ruff check .

.PHONY: typecheck
typecheck: ## mypy strict + tsc
	$(UV) run --group dev mypy
	$(PNPM) --filter studio-web typecheck

.PHONY: contracts-check
contracts-check: ## Validate handoff pack + fixture/schema conformance
	cd $(PACK) && ../../.venv/bin/python scripts/validate_pack.py \
	  --report planning/pack-validation-report.json
	$(PYTEST) tests/unit/test_contracts.py tests/unit/test_design_map.py -q
	$(UV) run python infra/ci/export_schema.py --check
	$(UV) run python infra/ci/check_relay_boundaries.py
	$(UV) run python packages/contracts/sync_contracts.py --check

.PHONY: schema-export
schema-export: ## Regenerate committed GraphQL schema from backend defs
	$(UV) run python infra/ci/export_schema.py

## ---------- test suites (separate per handoff §25.1) ----------

.PHONY: test-unit
test-unit: ## Unit tests (no DB required)
	$(PYTEST) services/studio-api/tests/unit -m "not integration" \
	  --timeout 120

.PHONY: test-integration
test-integration: db-up ## Integration tests (disposable PG in docker)
	$(PYTEST) services/studio-api/tests/integration -m integration \
	  --timeout 300

.PHONY: test-security
test-security: ## Authorization/safety tests
	$(PYTEST) services/studio-api/tests/security -m security \
	  --timeout 300

.PHONY: test-e2e
test-e2e: ## Browser journeys (Playwright; reports blocker if absent)
	@if [ -f tests/e2e/playwright.config.ts ]; then \
	  $(PNPM) --filter studio-web exec playwright test \
	    --config ../../tests/e2e/playwright.config.ts; \
	else \
	  echo "BLOCKED: playwright suite not installed (P02+); no result claimed"; \
	  exit 2; \
	fi

.PHONY: test-engines
test-engines: ## Engine adapter tests; explicit unavailability is honest
	@$(UV) run --extra engines python -c "import rdkit" 2>/dev/null || \
	  docker image inspect chem-studio-rdkit:2026.3.6 >/dev/null 2>&1 || { \
	  echo "UNAVAILABLE: no native rdkit and no chem-studio-rdkit image"; \
	  echo "  build: docker buildx build --platform linux/amd64 -t chem-studio-rdkit:2026.3.6 infra/images/rdkit"; \
	  echo "  see docs/dependencies.lock.md platform matrix"; exit 2; }
	$(PYTEST) services/studio-api/tests/engines -m engine --timeout 600

.PHONY: eval-smoke
eval-smoke: ## Evaluation smoke (fixture-only; non-scientific)
	@if [ -f tests/eval/smoke.py ]; then \
	  $(UV) run python tests/eval/smoke.py; \
	else \
	  echo "BLOCKED: eval harness arrives with P06; no result claimed"; \
	  exit 2; \
	fi

.PHONY: train-smoke
train-smoke: ## Training smoke; blocked without hardware/model (U08/U13)
	@$(UV) run --extra training python -c "import torch" 2>/dev/null || { \
	  echo "BLOCKED: training profile not installed (U08/U13)"; exit 2; }
	@if [ -f tests/eval/train_smoke.py ]; then \
	  $(UV) run --extra training python tests/eval/train_smoke.py; \
	else \
	  echo "BLOCKED: training smoke harness arrives with P08"; exit 2; \
	fi

.PHONY: backup-test
backup-test: db-up ## Dump+restore cycle on disposable DB
	$(UV) run python tests/integration/recovery/backup_restore_check.py

## ---------- aggregate ----------

.PHONY: verify-core
verify-core: lint contracts-check test-unit ## Deterministic checks, no GPU/net/lab
	@echo "verify-core: deterministic checks passed (unit+contracts+lint)"
