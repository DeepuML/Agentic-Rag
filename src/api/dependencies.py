"""
src/api/dependencies.py
────────────────────────
FastAPI dependency injection providers.
Services are initialized once and shared across requests.
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from src.core.config import Settings, get_settings
from src.core.vector_store import QdrantVectorStore
from src.guardrails.input.injection_detector import InjectionDetector
from src.guardrails.input.pii_redactor import PIIRedactor
from src.guardrails.input.decomposer import QueryDecomposer
from src.guardrails.output.grounding_validator import GroundingValidator
from src.guardrails.output.pii_leak_check import PIILeakChecker
from src.guardrails.output.safety_filter import ContentSafetyFilter
from src.memory.manager import MemoryManager, get_memory_manager
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Singleton Service Factories ───────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_vector_store_dep() -> QdrantVectorStore:
    """Return singleton QdrantVectorStore."""
    return QdrantVectorStore()


@lru_cache(maxsize=1)
def get_injection_detector() -> InjectionDetector:
    """Return singleton InjectionDetector."""
    return InjectionDetector(use_llm_fallback=True)


@lru_cache(maxsize=1)
def get_pii_redactor() -> PIIRedactor:
    """Return singleton PIIRedactor."""
    return PIIRedactor()


@lru_cache(maxsize=1)
def get_decomposer() -> QueryDecomposer:
    """Return singleton QueryDecomposer."""
    settings = get_settings()
    return QueryDecomposer(
        enabled=True,
        max_sub_questions=4,
        min_query_length=80,
    )


@lru_cache(maxsize=1)
def get_grounding_validator() -> GroundingValidator:
    """Return singleton GroundingValidator."""
    settings = get_settings()
    return GroundingValidator(strict_mode=settings.grounding_strict_mode)


@lru_cache(maxsize=1)
def get_pii_leak_checker() -> PIILeakChecker:
    """Return singleton PIILeakChecker."""
    return PIILeakChecker(block_on_detect=False)  # Redact, don't block by default


@lru_cache(maxsize=1)
def get_safety_filter() -> ContentSafetyFilter:
    """Return singleton ContentSafetyFilter."""
    return ContentSafetyFilter(use_llm_fallback=False)


# ── Request Context ───────────────────────────────────────────────────────────

async def get_request_id(request: Request) -> str:
    """Extract or generate request ID from headers."""
    return request.headers.get("X-Request-ID", "")


# ── Optional API Key Auth ─────────────────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Depends(_api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Optional API key verification.
    Only enforced in production mode.
    In development mode, all requests are allowed.
    """
    if not settings.is_production:
        return  # Skip auth in dev mode

    if not api_key or api_key != settings.api_secret_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "APIKey"},
        )
