SHELL := /bin/bash
.DEFAULT_GOAL := help

PY      ?= $(shell command -v python3.12 || command -v python3.13 || echo python3)
VENV    := backend/.venv
BIN     := $(VENV)/bin
PG_BIN  ?= $(firstword $(wildcard /opt/homebrew/opt/postgresql@17/bin /usr/local/opt/postgresql@17/bin /opt/homebrew/opt/postgresql@16/bin) \
             $(shell dirname "$$(command -v pg_ctl 2>/dev/null || echo /usr/bin/pg_ctl)"))
PGDATA  := .data/pg
PGPORT  := 5508
DB_URL  := postgresql+asyncpg://relay@127.0.0.1:$(PGPORT)/relay
TEST_DB := postgresql+asyncpg://relay@127.0.0.1:$(PGPORT)/relay_test
DEMO    := RELAY_CHAOS_MOUNT=true RELAY_CHAOS_VERIFY_SECRET=whsec_cmVsYXktZGVtby1zaWduaW5nLXNlY3JldC0wMQ==

.PHONY: help install db db-stop migrate seed traffic api dispatcher chaos web dev \
        test test-unit test-backend test-web lint typecheck build check up down

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create the Python venv and install backend + web dependencies
	test -d $(VENV) || $(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -e "backend[dev]"
	cd web && pnpm install

db: ## Start a local Postgres on :5508 with data in .data/pg (no Docker needed)
	@mkdir -p .data
	@test -d $(PGDATA) || $(PG_BIN)/initdb -D $(PGDATA) -U relay --auth=trust -E UTF8 >/dev/null
	@$(PG_BIN)/pg_ctl -D $(PGDATA) status >/dev/null 2>&1 || \
		$(PG_BIN)/pg_ctl -D $(PGDATA) -l .data/pg.log -o "-p $(PGPORT) -k /tmp -c listen_addresses=127.0.0.1 -c max_connections=200" start
	@sleep 1
	@psql -h 127.0.0.1 -p $(PGPORT) -U relay -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='relay'" | grep -q 1 || createdb -h 127.0.0.1 -p $(PGPORT) -U relay relay
	@psql -h 127.0.0.1 -p $(PGPORT) -U relay -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='relay_test'" | grep -q 1 || createdb -h 127.0.0.1 -p $(PGPORT) -U relay relay_test

db-stop: ## Stop the local Postgres
	$(PG_BIN)/pg_ctl -D $(PGDATA) stop

migrate: ## Apply Alembic migrations
	cd backend && RELAY_DATABASE_URL=$(DB_URL) .venv/bin/alembic upgrade head

seed: migrate ## Reset the database and load the demo tenant with a day of history
	cd backend && RELAY_DATABASE_URL=$(DB_URL) .venv/bin/relay-seed

traffic: ## Publish a steady stream of demo events (Ctrl-C to stop)
	cd backend && RELAY_DATABASE_URL=$(DB_URL) .venv/bin/relay-seed traffic

api: ## Run the API on :8108 with the chaos receiver mounted at /chaos
	cd backend && RELAY_DATABASE_URL=$(DB_URL) $(DEMO) .venv/bin/relay-api

dispatcher: ## Run the delivery dispatcher
	cd backend && RELAY_DATABASE_URL=$(DB_URL) .venv/bin/relay-dispatcher

web: ## Run the console on :3108
	cd web && RELAY_API_URL=http://127.0.0.1:8108 NEXT_PUBLIC_DEMO_MODE=true pnpm dev

dev: ## Run API, dispatcher and console together
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) --no-print-directory api & \
	$(MAKE) --no-print-directory dispatcher & \
	$(MAKE) --no-print-directory web & \
	wait

test: test-backend test-web ## Run every test suite

test-unit: ## Backend unit tests only (no database)
	cd backend && .venv/bin/pytest tests/unit -q

test-backend: ## Backend tests in a testcontainer; USE_LOCAL_PG=1 uses the `make db` server instead
	cd backend && $(if $(USE_LOCAL_PG),RELAY_TEST_DATABASE_URL=$(TEST_DB)) .venv/bin/pytest -q

test-web: ## Web unit tests
	cd web && pnpm test

lint: ## Ruff + ESLint
	cd backend && .venv/bin/ruff check src tests alembic && .venv/bin/ruff format --check src tests alembic
	cd web && pnpm lint

typecheck: ## mypy --strict + tsc --noEmit
	cd backend && .venv/bin/mypy
	cd web && pnpm typecheck

build: ## Production build of the console
	cd web && pnpm build

check: lint typecheck test build ## Everything CI runs

up: ## Full stack in Docker (Postgres, API, dispatcher, chaos receiver, console)
	docker compose up --build -d
	docker compose --profile seed run --rm seed

down: ## Stop the Docker stack
	docker compose down
