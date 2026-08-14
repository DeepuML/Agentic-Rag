"""
src/utils/metrics.py
────────────────────
Prometheus metrics definitions for the Agentic RAG system.
All counters, histograms, and gauges are defined here as module-level singletons.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

# ── Application Info ──────────────────────────────────────────────────────────
APP_INFO = Info("agentic_rag_app", "Application information")
APP_INFO.info({"version": "1.0.0", "python": "3.12"})

# ── HTTP Request Metrics ──────────────────────────────────────────────────────
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests processed",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ── Chat / Agent Metrics ──────────────────────────────────────────────────────
CHAT_REQUESTS_TOTAL = Counter(
    "chat_requests_total",
    "Total chat requests received",
    ["user_id"],
)

CHAT_ERRORS_TOTAL = Counter(
    "chat_errors_total",
    "Total chat requests that resulted in errors",
    ["error_type"],
)

AGENT_ITERATIONS = Histogram(
    "agent_iterations_total",
    "Number of agent graph iterations per request",
    buckets=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
)

AGENT_LATENCY = Histogram(
    "agent_latency_seconds",
    "End-to-end agent pipeline latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# ── Guardrail Metrics ─────────────────────────────────────────────────────────
GUARDRAIL_TRIGGERS = Counter(
    "guardrail_triggers_total",
    "Number of times a guardrail was triggered",
    ["guardrail_type", "direction"],  # direction: input | output
)

INJECTION_DETECTIONS = Counter(
    "injection_detections_total",
    "Number of prompt injection attempts detected",
    ["detection_method"],  # regex | llm
)

PII_REDACTIONS = Counter(
    "pii_redactions_total",
    "Number of PII entities redacted",
    ["entity_type", "location"],  # location: input | output
)

GROUNDING_FAILURES = Counter(
    "grounding_failures_total",
    "Number of times grounding validation failed",
)

# ── Vector Store Metrics ──────────────────────────────────────────────────────
VECTOR_STORE_OPS = Counter(
    "vector_store_operations_total",
    "Total Qdrant operations performed",
    ["operation", "collection"],  # operation: upsert | search | delete
)

RETRIEVAL_LATENCY = Histogram(
    "retrieval_latency_seconds",
    "Qdrant similarity search latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

DOCS_RETRIEVED = Histogram(
    "documents_retrieved_per_query",
    "Number of documents retrieved per query",
    buckets=[0, 1, 2, 3, 5, 10, 20],
)

# ── Memory Metrics ─────────────────────────────────────────────────────────────
MEMORY_OPS = Counter(
    "memory_operations_total",
    "Total memory read/write operations",
    ["memory_type", "operation"],  # memory_type: short_term | long_term
)

ACTIVE_SESSIONS = Gauge(
    "active_sessions",
    "Number of currently active chat sessions",
)

# ── Ingestion Metrics ─────────────────────────────────────────────────────────
INGESTION_RUNS = Counter(
    "ingestion_runs_total",
    "Total ingestion pipeline runs",
    ["connector", "status"],  # status: success | failure
)

DOCS_INGESTED = Counter(
    "documents_ingested_total",
    "Total documents ingested into vector store",
    ["connector"],
)
