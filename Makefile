# myTrakIn — common tasks. Run `make help`.
TEST_DB ?= postgresql://postgres@localhost:5432/mytrakin_test

.PHONY: help setup db-reset api web test lint build check api-docs

help:
	@echo "make setup     install API (venv) and web dependencies"
	@echo "make db-reset  rebuild the local test database from migrations + seed ($(TEST_DB))"
	@echo "make api       run the API on http://localhost:8000 (docs at /docs)"
	@echo "make web       run the web app on http://localhost:3000"
	@echo "make test      API tests against a fresh database"
	@echo "make lint      ruff + TypeScript checks"
	@echo "make build     production build of the web app"
	@echo "make check     everything CI runs"
	@echo "make api-docs  regenerate docs/api-reference.md"

setup:
	cd apps/api && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
	cd apps/web && npm install

db-reset:
	scripts/db-local-reset.sh $(TEST_DB)

api:
	cd apps/api && .venv/bin/uvicorn app.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

test:
	cd apps/api && TEST_DATABASE_URL=$(TEST_DB) .venv/bin/pytest -q

lint:
	cd apps/api && .venv/bin/ruff check .
	cd apps/web && npm run typecheck

build:
	cd apps/web && npm run build

check: lint test build

api-docs:
	cd apps/api && .venv/bin/python ../../scripts/gen-api-reference.py
