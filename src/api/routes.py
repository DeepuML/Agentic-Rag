"""
src/api/routes.py
─────────────────
FastAPI route definitions:
  POST /chat     - Main RAG pipeline with guardrails
  POST /reset    - Clear session state
  GET  /health   - Health check
  POST /ingest/trigger - Trigger manual ingestion
  GET  /metrics  - Prometheus metrics endpoint
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from langchain_core.documents import Document
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from src.agents.graph import get_compiled_graph
from src.agents.state import create_initial_state
from src.api.dependencies import (
    get_decomposer,
    get_grounding_validator,
    get_injection_detector,
    get_pii_leak_checker,
    get_pii_redactor,
    get_request_id,
    get_safety_filter,
    verify_api_key,
)
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    GuardrailFlags,
    HealthResponse,
    IngestResponse,
    IngestTriggerRequest,
    ResetRequest,
    ResetResponse,
    SourceDocument,
)
from src.core.exceptions import (
    ContentSafetyError,
    GroundingError,
    InjectionDetectedError,
    PIIDetectedError,
)
from src.guardrails.input.decomposer import QueryDecomposer
from src.guardrails.input.injection_detector import InjectionDetector
from src.guardrails.input.pii_redactor import PIIRedactor
from src.guardrails.output.grounding_validator import GroundingValidator
from src.guardrails.output.pii_leak_check import PIILeakChecker
from src.guardrails.output.safety_filter import ContentSafetyFilter
from src.memory.manager import get_memory_manager
from src.utils.helpers import timer
from src.utils.logger import get_request_logger
from src.utils.metrics import (
    ACTIVE_SESSIONS,
    AGENT_LATENCY,
    CHAT_ERRORS_TOTAL,
    CHAT_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_TOTAL,
)

router = APIRouter()

# ── POST /chat ────────────────────────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Agentic RAG Chat",
    description=(
        "Submit a query that runs through the full pipeline: "
        "Input Guardrails → Agent (Plan→Retrieve→Evaluate→Reflect→Generate) → Output Guardrails. "
        "Returns a grounded, safe answer with source attribution."
    ),
    tags=["Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def chat(
    request: ChatRequest,
    injection_detector: InjectionDetector = Depends(get_injection_detector),
    pii_redactor: PIIRedactor = Depends(get_pii_redactor),
    decomposer: QueryDecomposer = Depends(get_decomposer),
    grounding_validator: GroundingValidator = Depends(get_grounding_validator),
    pii_checker: PIILeakChecker = Depends(get_pii_leak_checker),
    safety_filter: ContentSafetyFilter = Depends(get_safety_filter),
) -> ChatResponse:
    """
    Main chat endpoint.

    Pipeline:
        1. Input: Injection detection → PII redaction → Query decomposition
        2. Agent: LangGraph (Plan → Retrieve → Evaluate → Reflect → Generate)
        3. Output: PII leak check → Grounding validation → Content safety
    """
    log = get_request_logger(__name__, request.user_id, request.session_id)
    CHAT_REQUESTS_TOTAL.labels(user_id=request.user_id).inc()
    ACTIVE_SESSIONS.inc()

    flags = GuardrailFlags()
    start_time = time.perf_counter()

    try:
        # ── STAGE 1: Input Guardrails ─────────────────────────────────────────

        # 1a. Injection Detection
        log.info("Running injection detection")
        try:
            injection_result = injection_detector.check(request.query, raise_on_detect=True)
        except InjectionDetectedError as e:
            log.warning("Injection blocked", extra={"trigger": e.trigger})
            CHAT_ERRORS_TOTAL.labels(error_type="injection").inc()
            return ChatResponse(
                session_id=request.session_id,
                user_id=request.user_id,
                answer="Your request was blocked because it contains patterns associated with prompt injection attacks.",
                is_blocked=True,
                block_reason=f"Injection detected: {e.trigger}",
                guardrail_flags=GuardrailFlags(injection_detected=True),
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )

        # 1b. PII Redaction on Input
        log.info("Running PII redaction on input")
        pii_input_result = pii_redactor.redact(request.query, location="input")
        safe_query = pii_input_result.redacted_text
        if pii_input_result.has_pii:
            flags.pii_redacted = True
            flags.pii_entities_found = [e["entity_type"] for e in pii_input_result.entities_found]
            log.info("PII redacted from input", extra={"entity_count": len(pii_input_result.entities_found)})

        # 1c. Query Decomposition
        log.info("Running query decomposition")
        decomp_result = decomposer.decompose(safe_query)
        if decomp_result.was_decomposed:
            flags.query_decomposed = True
            flags.sub_questions = decomp_result.sub_questions
            log.info("Query decomposed", extra={"sub_questions": len(decomp_result.sub_questions)})

        # Save user message to memory
        memory = get_memory_manager()
        memory.add_user_message(request.user_id, request.session_id, request.query)

        # Load conversation history for context
        history = memory.get_formatted_history(request.user_id, request.session_id)
        user_context = memory.get_user_context(request.user_id, safe_query)

        # ── STAGE 2: Agent Execution ──────────────────────────────────────────

        log.info("Starting agent graph execution")
        agent_start = time.perf_counter()

        initial_state = create_initial_state(
            query=decomp_result.primary_query,
            user_id=request.user_id,
            session_id=request.session_id,
            sub_questions=decomp_result.sub_questions,
            max_iterations=request.max_iterations,
        )

        graph = get_compiled_graph()
        final_state = graph.invoke(initial_state)

        agent_elapsed = time.perf_counter() - agent_start
        AGENT_LATENCY.observe(agent_elapsed)

        raw_answer: str = final_state.get("answer", "")
        context_docs: list[Document] = final_state.get("all_docs", [])
        iterations: int = final_state.get("iterations", 0)

        log.info(
            "Agent execution complete",
            extra={"iterations": iterations, "answer_len": len(raw_answer)},
        )

        if not raw_answer:
            raw_answer = (
                "I was unable to find relevant information to answer your question. "
                "Please try rephrasing or check if data has been ingested."
            )

        # ── STAGE 3: Output Guardrails ────────────────────────────────────────

        safe_answer = raw_answer

        # 3a. PII Leak Check on Output
        log.info("Running PII leak check on output")
        safe_answer, pii_output_result = pii_checker.check(safe_answer)
        if pii_output_result.has_pii:
            flags.pii_redacted = True
            log.info("PII redacted from output")

        # 3b. Content Safety Check
        log.info("Running content safety check")
        try:
            safety_result = safety_filter.check(safe_answer, raise_on_unsafe=True)
            flags.safety_passed = safety_result.is_safe
        except ContentSafetyError as e:
            log.warning("Safety filter triggered", extra={"category": e.category})
            CHAT_ERRORS_TOTAL.labels(error_type="safety").inc()
            return ChatResponse(
                session_id=request.session_id,
                user_id=request.user_id,
                answer="I'm unable to provide this response due to content safety policies.",
                is_blocked=True,
                block_reason=f"Content safety: {e.category}",
                guardrail_flags=GuardrailFlags(safety_passed=False, triggered_safety_category=e.category),
                iterations=iterations,
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )

        # 3c. Grounding Validation
        log.info("Running grounding validation")
        try:
            grounding_result = grounding_validator.validate(
                safe_answer,
                context_docs,
                raise_on_failure=False,  # Don't raise; use refusal message instead
            )
            flags.grounding_score = grounding_result.grounding_score
            flags.grounding_passed = grounding_result.is_grounded

            if not grounding_result.is_grounded:
                log.warning(
                    "Grounding failed",
                    extra={
                        "score": grounding_result.grounding_score,
                        "ungrounded_ratio": grounding_result.ungrounded_ratio,
                    },
                )
                safe_answer = (
                    "I cannot provide a reliable answer because the available information does not "
                    "sufficiently support a confident response. Please refine your query or check "
                    "the source data."
                )
        except GroundingError as e:
            log.warning("Grounding error", extra={"error": str(e)})
            flags.grounding_passed = False
            safe_answer = "I cannot verify this answer against the available source documents."

        # ── Save Assistant Response to Memory ─────────────────────────────────
        memory.add_assistant_message(request.user_id, request.session_id, safe_answer)

        # ── Build Source Attribution ──────────────────────────────────────────
        sources: list[SourceDocument] = []
        if request.include_sources and context_docs:
            seen_source_ids: set[str] = set()
            for doc in context_docs[:5]:
                sid = doc.metadata.get("source_id", "")
                if sid and sid not in seen_source_ids:
                    seen_source_ids.add(sid)
                    sources.append(
                        SourceDocument(
                            source=doc.metadata.get("source", ""),
                            source_id=sid,
                            title=doc.metadata.get("title", ""),
                            score=doc.metadata.get("_score", 0.0),
                            url=doc.metadata.get("url", ""),
                        )
                    )

        total_elapsed_ms = (time.perf_counter() - start_time) * 1000
        HTTP_REQUEST_DURATION.labels(method="POST", endpoint="/chat").observe(
            total_elapsed_ms / 1000
        )
        HTTP_REQUESTS_TOTAL.labels(method="POST", endpoint="/chat", status_code="200").inc()

        log.info("Chat request complete", extra={"latency_ms": round(total_elapsed_ms, 1)})

        return ChatResponse(
            session_id=request.session_id,
            user_id=request.user_id,
            answer=safe_answer,
            sources=sources,
            guardrail_flags=flags,
            iterations=iterations,
            latency_ms=round(total_elapsed_ms, 1),
            is_blocked=False,
        )

    except Exception as e:
        CHAT_ERRORS_TOTAL.labels(error_type="unexpected").inc()
        log.error("Unexpected error in chat endpoint", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}",
        )
    finally:
        ACTIVE_SESSIONS.dec()


# ── POST /reset ───────────────────────────────────────────────────────────────

@router.post(
    "/reset",
    response_model=ResetResponse,
    summary="Reset Session State",
    description="Clear Redis conversation history and optionally Qdrant user documents for a session.",
    tags=["Session"],
    dependencies=[Depends(verify_api_key)],
)
async def reset_session(request: ResetRequest) -> ResetResponse:
    """
    Clear all memory for a specific user session.

    - Always clears: Redis short-term conversation history.
    - Optional: Qdrant user documents (set clear_vector_store=True).
    """
    memory = get_memory_manager()
    cleared = memory.clear_session(request.user_id, request.session_id)

    if request.clear_vector_store:
        try:
            from src.core.vector_store import QdrantVectorStore
            from src.core.config import get_settings
            vs = QdrantVectorStore()
            settings = get_settings()
            deleted = vs.delete_by_metadata(
                filter_conditions={"user_id": request.user_id},
                collection_name=settings.qdrant_collection_name,
            )
            cleared["vector_store"] = True
        except Exception as e:
            cleared["vector_store"] = False

    HTTP_REQUESTS_TOTAL.labels(method="POST", endpoint="/reset", status_code="200").inc()

    return ResetResponse(
        user_id=request.user_id,
        session_id=request.session_id,
        cleared=cleared,
        message=f"Session {request.session_id!r} for user {request.user_id!r} has been reset.",
    )


# ── GET /health ───────────────────────────────────────────────────────────────

_start_time = time.time()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns service health status including Qdrant and Redis connectivity.",
    tags=["System"],
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.
    Returns status of app, Qdrant, and Redis.
    """
    services: dict[str, str] = {}

    # Check Redis
    try:
        memory = get_memory_manager()
        health = memory.health_check()
        services["redis"] = "healthy" if health.get("redis") else "unhealthy"
    except Exception:
        services["redis"] = "unhealthy"

    # Check Qdrant
    try:
        from src.core.vector_store import QdrantVectorStore
        from src.core.config import get_settings
        vs = QdrantVectorStore()
        settings = get_settings()
        vs.ensure_collection(settings.qdrant_collection_name)
        services["qdrant"] = "healthy"
    except Exception:
        services["qdrant"] = "unhealthy"

    all_healthy = all(v == "healthy" for v in services.values())

    HTTP_REQUESTS_TOTAL.labels(method="GET", endpoint="/health", status_code="200").inc()

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        version="1.0.0",
        services=services,
        uptime_seconds=round(time.time() - _start_time, 1),
    )


# ── POST /ingest/trigger ──────────────────────────────────────────────────────

@router.post(
    "/ingest/trigger",
    response_model=IngestResponse,
    summary="Trigger Data Ingestion",
    description="Manually trigger a data ingestion cycle for specified connectors.",
    tags=["Ingestion"],
    dependencies=[Depends(verify_api_key)],
)
async def trigger_ingestion(
    request: IngestTriggerRequest = IngestTriggerRequest(),
) -> IngestResponse:
    """
    Manually trigger an ingestion cycle.
    Runs synchronously (for quick dev testing) — in production consider async task queue.
    """
    from src.data_ingestion.pipeline import IngestionPipeline
    from src.data_ingestion.connectors import GmailConnector, NotionConnector, JiraConnector

    connector_map = {
        "gmail": GmailConnector(),
        "notion": NotionConnector(),
        "jira": JiraConnector(),
    }

    selected_connectors = [
        connector_map[name]
        for name in request.connectors
        if name in connector_map
    ]

    pipeline = IngestionPipeline(connectors=selected_connectors)
    summary = pipeline.run_once()

    HTTP_REQUESTS_TOTAL.labels(method="POST", endpoint="/ingest/trigger", status_code="200").inc()

    return IngestResponse(
        message="Ingestion cycle complete",
        summary=summary,
    )


# ── GET /metrics ──────────────────────────────────────────────────────────────

@router.get(
    "/metrics",
    summary="Prometheus Metrics",
    description="Prometheus-compatible metrics scrape endpoint.",
    tags=["Observability"],
    include_in_schema=False,  # Don't expose in Swagger UI
)
async def metrics() -> Response:
    """Return Prometheus metrics in text format."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
