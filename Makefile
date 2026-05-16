# Makefile for Mira Kontext Testing Bot

.PHONY: help install install-dev test lint format typecheck check repl chat test-api status query clean

help:
	@echo "Available targets:"
	@echo "  install      Install dependencies with Poetry"
	@echo "  install-dev  Install with dev dependencies"
	@echo "  test         Run pytest test suite"
	@echo "  lint         Run ruff linter"
	@echo "  format       Format code with ruff"
	@echo "  typecheck    Run pyright type checker"
	@echo "  check        Run all checks (lint, format, typecheck)"
	@echo "  chat         Start interactive chat mode"
	@echo "  test-api     Run full test suite against API"
	@echo "  status       Check API status"
	@echo "  query (Q=...) Run a single query"
	@echo "  repl         Start IPython REPL with bot loaded (uses repl-toolkit)"
	@echo "  clean        Clean build artifacts"

install:
	poetry install --no-dev

install-dev:
	poetry install

test:
	poetry run pytest -v

lint:
	poetry run ruff check src tests

format:
	poetry run ruff format src tests

typecheck:
	poetry run pyright src

check: lint format typecheck
	@echo "All checks passed!"

chat:
	poetry run python -m mira_kontext_testing_bot chat

test-api:
	poetry run python -m mira_kontext_testing_bot test full

status:
	poetry run python -m mira_kontext_testing_bot status

repl:
	@echo "Starting IPython REPL with repl-toolkit..."
	poetry run python -c "import IPython, repl_toolkit" >/dev/null 2>&1 || poetry install
	poetry run python repl.py

query:
	poetry run python -m mira_kontext_testing_bot query "$(Q)"

clean:
	rm -rf build/ dist/ __pycache__/ .pytest_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
