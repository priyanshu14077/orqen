.DEFAULT_GOAL := help
.PHONY: help install up down nuke test-db migrate migrate-status seed streams setup gateway proxy test test-unit lint fmt typecheck check

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install the workspace and dev tools
	uv sync

up: ## Start Redis, wait until healthy
	docker compose up -d --wait

down: ## Stop all containers, keep Redis data
	docker compose --profile test down

nuke: ## Stop all containers and delete Redis data
	docker compose --profile test down -v

test-db: ## Start the throwaway Postgres that integration tests rebuild
	docker compose --profile test up -d --wait postgres-test

migrate: ## Apply migrations to Supabase
	uv run alembic upgrade head

migrate-status: ## Show the Supabase schema revision
	uv run alembic current

seed: ## Load dev tenants, users and the starter problem (idempotent)
	uv run python -m scripts.seed

streams: ## Create Redis streams and consumer groups (idempotent)
	uv run orqen-workers bootstrap

setup: up migrate seed streams ## Everything a fresh clone needs

gateway: ## Run the gateway on :8000 with reload
	uv run uvicorn orqen_gateway.app:app --reload --port 8000

proxy: ## Run the LLM proxy on :8080 with reload
	uv run uvicorn orqen_proxy.app:app --reload --port 8080

test: ## All tests; integration tests need `make up test-db`
	uv run pytest

test-unit: ## Tests that need no containers
	uv run pytest -m "not integration"

lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Fix lint and formatting
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## mypy, strict
	uv run mypy

check: lint typecheck test ## What CI runs
