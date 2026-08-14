# Agentic RAG over Live Data

> **Production-ready Agentic Retrieval-Augmented Generation** with live data ingestion from Gmail, Notion & Jira — powered by LangGraph, FastAPI, Qdrant, and strict Input/Output Guardrails.

---

## Project Architecture

### Directory Structure

```
agentic-rag-live/
├── .env                            # Environment variables (secrets — never commit)
├── .gitignore
├── docker-compose.yml              # All services: app, qdrant, redis, prometheus, grafana
├── Dockerfile                      # Multi-stage build
├── Makefile                        # Developer workflow commands
├── pyproject.toml                  # Project metadata, linter & test configuration
├── requirements.txt                # Pinned Python dependencies
├── README.md
│
├── configs/
│   ├── guardrails.yaml             # PII thresholds, injection trigger words, safety rules
│   ├── connectors.yaml             # Gmail / Notion / Jira connection settings
│   └── logging.yaml                # Structured logging configuration
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application entrypoint & lifespan
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py         # FastAPI dependency injection (services, auth)
│   │   ├── routes.py               # POST /chat, POST /reset, GET /health
│   │   └── schemas.py              # Pydantic request/response models
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Pydantic Settings — single source of truth
│   │   ├── vector_store.py         # Qdrant client wrapper & collection management
│   │   └── exceptions.py           # Domain exceptions (GroundingError, PIIError, etc.)
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py                # AgentState TypedDict definition
│   │   ├── nodes.py                # 5 nodes: planner, retriever, evaluator, reflector, generator
│   │   ├── tools.py                # LangChain tools wrapping Qdrant retrieval
│   │   └── graph.py                # LangGraph StateGraph compilation & conditional edges
│   │
│   ├── data_ingestion/
│   │   ├── __init__.py
│   │   ├── base_connector.py       # Abstract base class for all connectors
│   │   ├── pipeline.py             # Infinite ingestion loop (60s poll interval)
│   │   ├── chunking.py             # Text chunking strategies
│   │   └── connectors/
│   │       ├── __init__.py
│   │       ├── gmail_connector.py  # Gmail OAuth2 connector (mock-ready)
│   │       ├── notion_connector.py # Notion API connector (mock-ready)
│   │       └── jira_connector.py   # Jira REST API connector (mock-ready)
│   │
│   ├── guardrails/
│   │   ├── __init__.py
│   │   ├── input/
│   │   │   ├── __init__.py
│   │   │   ├── injection_detector.py  # Regex + LLM fallback injection detection
│   │   │   ├── pii_redactor.py        # Presidio analyzer + anonymizer
│   │   │   └── decomposer.py          # LLM-based query decomposition
│   │   └── output/
│   │       ├── __init__.py
│   │       ├── pii_leak_check.py      # Post-generation PII scan
│   │       ├── grounding_validator.py # Fact-checking against retrieved docs
│   │       └── safety_filter.py       # Content safety classification
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── manager.py              # Unified memory interface
│   │   ├── short_term.py           # Redis — last 5 conversation turns
│   │   └── long_term.py            # Qdrant — user preferences & summaries
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py               # Structured logging setup
│       ├── metrics.py              # Prometheus metrics definitions
│       └── helpers.py              # Shared utility functions
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures & test app setup
│   ├── unit/
│   │   ├── guardrails/             # Unit tests for all guardrail components
│   │   └── agents/                 # Unit tests for agent nodes and graph
│   └── adversarial/
│       └── injection_payloads.json # 20+ adversarial prompt injection test cases
│
├── scripts/
│   ├── reset_env.py                # CLI tool to clear Redis/Qdrant state
│   └── seed_data.py                # Seed Qdrant with sample documents
│
└── evaluation/
    ├── ragas_pipeline.py           # RAGAS evaluation: context_relevancy, answer_faithfulness
    └── datasets/
        └── qa_validation.json      # Ground-truth Q&A pairs for evaluation
```

---

## Quick Start

### Prerequisites
- Docker & Docker Compose v2+
- Python 3.12+
- Make

### 1. Clone and configure

```bash
git clone https://github.com/your-org/agentic-rag-live.git
cd agentic-rag-live

# Copy environment template and fill in your API keys
cp .env .env.local  # edit .env with your actual keys
```

### 2. Start infrastructure

```bash
make up-infra   # starts Qdrant, Redis, Prometheus, Grafana
```

### 3. Install & run locally

```bash
make install    # installs Python deps + spaCy model
make seed-data  # seeds Qdrant with sample data
make run-dev    # starts FastAPI with hot-reload at http://localhost:8000
```

### 4. Or run everything in Docker

```bash
make build && make up
```

---

## 🔌 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/docs` | Interactive Swagger UI |
| `POST` | `/chat` | Main chat endpoint with full RAG pipeline |
| `POST` | `/reset` | Clear session state (Redis + Qdrant) |
| `POST` | `/ingest/trigger` | Manually trigger data ingestion |
| `GET` | `/metrics` | Prometheus metrics scrape endpoint |

### Chat Request Example

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "session_id": "session_abc",
    "query": "Summarize all my open Jira tickets from last week"
  }'
```

### Response

```json
{
  "session_id": "session_abc",
  "answer": "Here are your open Jira tickets from last week: ...",
  "sources": ["PROJ-101", "PROJ-102"],
  "guardrail_flags": {
    "injection_detected": false,
    "pii_redacted": false,
    "grounding_score": 0.92,
    "safety_passed": true
  },
  "latency_ms": 843
}
```

---

## Guardrails Pipeline

```
User Query
    │
    ▼
┌─────────────────────────────┐
│   INPUT GUARDRAILS           │
│  1. Injection Detection      │  ← Regex + LLM fallback
│  2. PII Redaction (Presidio) │  ← Replace emails/phones
│  3. Query Decomposition      │  ← Split complex queries
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│   AGENTIC RAG PIPELINE       │
│  Plan → Retrieve → Evaluate  │
│  → Reflect → Generate        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│   OUTPUT GUARDRAILS          │
│  1. PII Leak Check           │  ← Presidio on output
│  2. Grounding Validation     │  ← Facts vs. retrieved docs
│  3. Content Safety Filter    │  ← Harmful content check
└──────────────┬──────────────┘
               │
               ▼
          Safe Answer
```

---

## Agent Graph

The LangGraph `StateGraph` implements a Plan-Retrieve-Evaluate-Reflect-Generate loop:

```
START
  │
  ▼
planner ──► retriever ──► evaluator
                               │
                    ┌──────────┴──────────┐
                    │ sufficient?          │ not sufficient (max 3 retries)
                    ▼                     ▼
                generator            reflector ──► retriever (retry)
                    │
                    ▼
                   END
```

---

## Configuration

All guardrail thresholds are in [`configs/guardrails.yaml`](configs/guardrails.yaml):

```yaml
pii_threshold: 0.85
injection_trigger_words:
  - "ignore previous instructions"
  - "drop all tables"
grounding_strict_mode: true
```

---

## 📊 Observability

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3000 | Dashboards (admin/admin) |
| Prometheus | http://localhost:9090 | Metrics scraping |
| App Metrics | http://localhost:8000/metrics | Raw Prometheus metrics |
| Swagger UI | http://localhost:8000/docs | API documentation |

---

##  Testing

```bash
make test              # All tests with coverage
make test-unit         # Unit tests only
make test-adversarial  # Adversarial injection tests
make eval              # RAGAS evaluation pipeline
```

---

##  Makefile Commands

| Command | Description |
|---------|-------------|
| `make install` | Install Python dependencies |
| `make run` | Start app (production mode) |
| `make run-dev` | Start app (hot-reload dev mode) |
| `make up` | Start all Docker services |
| `make down` | Stop all Docker services |
| `make test` | Run tests with coverage |
| `make reset` | Clear Redis + Qdrant state |
| `make seed-data` | Seed sample data |
| `make eval` | Run RAGAS evaluation |
| `make lint` | Run ruff linter |
| `make format` | Format with black + isort |

---

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `langgraph` | Agentic workflow state machine |
| `langchain` | LLM abstractions & tools |
| `fastapi` | High-performance REST API |
| `qdrant-client` | Vector database client |
| `redis` | Short-term memory cache |
| `presidio-analyzer` | PII detection |
| `presidio-anonymizer` | PII redaction |
| `ragas` | RAG evaluation metrics |
| `prometheus-client` | Metrics instrumentation |

---

## License

MIT License — see [LICENSE](LICENSE) for details.
