# ============================================================
# Makefile for Agentic RAG over Live Data
# ============================================================
.PHONY: help install run run-dev test test-unit test-adversarial \
        reset reset-all lint format type-check build up down \
        logs seed-data eval clean

SHELL := /bin/bash
APP_PORT ?= 8000
PYTHON := python3
PIP := pip3

# Default target
help: ## Show this help message
	@echo "═══════════════════════════════════════════════════════════════"
	@echo "  Agentic RAG over Live Data - Development Commands"
	@echo "═══════════════════════════════════════════════════════════════"
	@awk 'BEGIN {FS = ":.*##"; printf "\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

# ── Setup ──────────────────────────────────────────────────────────────────────
install: ## Install all Python dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	python -m spacy download en_core_web_lg
	@echo "✅ Installation complete."

install-dev: ## Install dev dependencies (includes linters, test tools)
	$(PIP) install -r requirements.txt
	$(PIP) install pytest pytest-asyncio pytest-cov httpx ruff mypy black isort
	python -m spacy download en_core_web_lg
	@echo "✅ Dev installation complete."

# ── Running ────────────────────────────────────────────────────────────────────
run: ## Run the app with Uvicorn (production-like)
	uvicorn src.main:app --host 0.0.0.0 --port $(APP_PORT) --workers 2

run-dev: ## Run the app in development mode (auto-reload)
	uvicorn src.main:app --host 0.0.0.0 --port $(APP_PORT) --reload --log-level debug

# ── Docker ─────────────────────────────────────────────────────────────────────
build: ## Build Docker images
	docker compose build

up: ## Start all Docker services (app + infra)
	docker compose up -d
	@echo "✅ Services started. App at http://localhost:$(APP_PORT)"

down: ## Stop all Docker services
	docker compose down

logs: ## Tail Docker logs for the app service
	docker compose logs -f app

up-infra: ## Start only infrastructure (Qdrant, Redis, Prometheus, Grafana)
	docker compose up -d qdrant redis prometheus grafana
	@echo "✅ Infrastructure started."

# ── Testing ────────────────────────────────────────────────────────────────────
test: ## Run all tests with coverage
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

test-unit: ## Run unit tests only
	pytest tests/unit/ -v

test-adversarial: ## Run adversarial injection tests
	pytest tests/adversarial/ -v -s

# ── Code Quality ───────────────────────────────────────────────────────────────
lint: ## Run ruff linter
	ruff check src/ tests/

format: ## Format code with black + isort
	black src/ tests/ scripts/ evaluation/
	isort src/ tests/ scripts/ evaluation/

type-check: ## Run mypy type checks
	mypy src/ --ignore-missing-imports

# ── Reset & Cleanup ────────────────────────────────────────────────────────────
reset: ## Reset Redis and Qdrant for a clean state (keeps services running)
	$(PYTHON) scripts/reset_env.py --clear-redis --clear-qdrant
	@echo "✅ Environment reset complete."

reset-all: ## Full reset: stop services, remove volumes, restart
	docker compose down -v
	docker compose up -d qdrant redis
	@echo "✅ Full environment reset. Volumes cleared."

clean: ## Remove Python caches and build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage dist build *.egg-info
	@echo "✅ Clean complete."

# ── Data & Evaluation ──────────────────────────────────────────────────────────
seed-data: ## Seed Qdrant with sample data for development
	$(PYTHON) scripts/seed_data.py
	@echo "✅ Sample data seeded."

eval: ## Run RAGAS evaluation pipeline
	$(PYTHON) evaluation/ragas_pipeline.py
	@echo "✅ Evaluation complete. Check evaluation/results/."
