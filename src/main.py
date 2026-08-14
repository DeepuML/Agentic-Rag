"""
src/main.py
────────────
FastAPI application entrypoint.
Sets up the app, middleware, lifespan events, and mounts the router.
"""
from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import router
from src.core.config import get_settings
from src.core.exceptions import AgenticRAGError
from src.core.vector_store import QdrantVectorStore
from src.data_ingestion.pipeline import IngestionPipeline
from src.utils.logger import configure_logging, get_logger

# Initialize logging first
configure_logging()
logger = get_logger(__name__)

settings = get_settings()

# ── Background ingestion thread ───────────────────────────────────────────────

_ingestion_pipeline: IngestionPipeline | None = None
_ingestion_thread: threading.Thread | None = None


def _start_ingestion_background() -> None:
    """Start the ingestion pipeline in a background daemon thread."""
    global _ingestion_pipeline, _ingestion_thread

    _ingestion_pipeline = IngestionPipeline()

    _ingestion_thread = threading.Thread(
        target=_ingestion_pipeline.run_loop,
        daemon=True,
        name="ingestion-loop",
    )
    _ingestion_thread.start()
    logger.info(
        "Background ingestion thread started",
        extra={"interval": settings.ingestion_poll_interval_seconds},
    )


def _stop_ingestion_background() -> None:
    """Signal the background ingestion loop to stop."""
    global _ingestion_pipeline
    if _ingestion_pipeline:
        _ingestion_pipeline.stop()
        logger.info("Ingestion pipeline stop signal sent")


# ── Application Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Handles startup tasks (DB init, ingestion thread) and
    shutdown tasks (graceful stop).
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("═══════════════════════════════════════════")
    logger.info("  Agentic RAG over Live Data — Starting Up")
    logger.info("═══════════════════════════════════════════")
    logger.info("Configuration", extra={
        "env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "mock_connectors": settings.use_mock_connectors,
    })

    # Initialize Qdrant collections
    try:
        vs = QdrantVectorStore()
        vs.ensure_collection(settings.qdrant_collection_name)
        vs.ensure_collection(settings.qdrant_memory_collection)
        logger.info("Qdrant collections initialized")
    except Exception as e:
        logger.warning("Qdrant initialization failed (non-fatal)", extra={"error": str(e)})

    # Start background ingestion
    _start_ingestion_background()

    logger.info("Application startup complete. Ready to serve requests.")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Application shutting down...")
    _stop_ingestion_background()
    logger.info("Shutdown complete.")


# ── FastAPI Application ───────────────────────────────────────────────────────

app = FastAPI(
    title="Agentic RAG over Live Data",
    description=(
        "Production-ready Agentic RAG system with live data ingestion from Gmail, Notion, and Jira. "
        "Features strict Input/Output Guardrails, LangGraph agent workflow, "
        "short-term (Redis) and long-term (Qdrant) memory, and full observability."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "Engineering Team",
        "email": "engineering@company.com",
    },
    license_info={"name": "MIT"},
)

# ── Middleware ────────────────────────────────────────────────────────────────

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression for responses > 1KB
app.add_middleware(GZipMiddleware, minimum_size=1024)


# ── Request Logging Middleware ────────────────────────────────────────────────

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log every request with timing information."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "HTTP request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": round(elapsed_ms, 1),
            "client": request.client.host if request.client else "unknown",
        },
    )
    response.headers["X-Response-Time-Ms"] = str(round(elapsed_ms, 1))
    return response


# ── Global Exception Handlers ─────────────────────────────────────────────────

@app.exception_handler(AgenticRAGError)
async def agentic_rag_error_handler(request: Request, exc: AgenticRAGError) -> JSONResponse:
    """Handle all domain-specific errors gracefully."""
    logger.warning(
        "Domain error handled",
        extra={"error_type": type(exc).__name__, "message": exc.message},
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": exc.message,
            "error_type": type(exc).__name__,
            "details": exc.details,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors without leaking internal details."""
    logger.error(
        "Unhandled exception",
        extra={"error": str(exc), "path": request.url.path},
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An internal server error occurred.",
            "error_type": "InternalServerError",
        },
    )


# ── Mount Router ──────────────────────────────────────────────────────────────

app.include_router(router, prefix="")


# ── Root Endpoint ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    """Redirect hint for API root."""
    return {
        "message": "Agentic RAG over Live Data API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
