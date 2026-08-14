"""
src/api/schemas.py
──────────────────
Pydantic request/response models for the FastAPI routes.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# ── Request Models ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Request body for POST /chat."""

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Unique identifier for the user",
        examples=["user_123"],
    )
    session_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Unique session identifier for conversation continuity",
        examples=["session_abc"],
    )
    query: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="The user's question or request",
        examples=["Summarize all my open Jira tickets from last week"],
    )
    max_iterations: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum agent iteration count for the retrieve→evaluate loop",
    )
    include_sources: bool = Field(
        default=True,
        description="Whether to include source document metadata in the response",
    )

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace")
        return v.strip()


class ResetRequest(BaseModel):
    """Request body for POST /reset."""

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="User ID whose session to reset",
    )
    session_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Session ID to reset (clears Redis history)",
    )
    clear_vector_store: bool = Field(
        default=False,
        description="If True, also clears the user's Qdrant documents (dangerous!)",
    )


class IngestTriggerRequest(BaseModel):
    """Request body for POST /ingest/trigger."""
    connectors: list[str] = Field(
        default=["gmail", "notion", "jira"],
        description="Which connectors to run",
    )


# ── Response Models ───────────────────────────────────────────────────────────

class GuardrailFlags(BaseModel):
    """Guardrail metadata attached to every chat response."""
    injection_detected: bool = False
    pii_redacted: bool = False
    pii_entities_found: list[str] = Field(default_factory=list)
    grounding_score: float = 1.0
    grounding_passed: bool = True
    safety_passed: bool = True
    triggered_safety_category: str | None = None
    query_decomposed: bool = False
    sub_questions: list[str] = Field(default_factory=list)


class SourceDocument(BaseModel):
    """A source document referenced in the answer."""
    source: str
    source_id: str
    title: str
    score: float = 0.0
    url: str = ""


class ChatResponse(BaseModel):
    """Response from POST /chat."""
    session_id: str
    user_id: str
    answer: str
    sources: list[SourceDocument] = Field(default_factory=list)
    guardrail_flags: GuardrailFlags = Field(default_factory=GuardrailFlags)
    iterations: int = 0
    latency_ms: float = 0.0
    is_blocked: bool = False
    block_reason: str | None = None


class ResetResponse(BaseModel):
    """Response from POST /reset."""
    user_id: str
    session_id: str
    cleared: dict[str, bool]
    message: str


class HealthResponse(BaseModel):
    """Response from GET /health."""
    status: str
    version: str = "1.0.0"
    services: dict[str, str] = Field(default_factory=dict)
    uptime_seconds: float = 0.0


class IngestResponse(BaseModel):
    """Response from POST /ingest/trigger."""
    message: str
    summary: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Generic error response."""
    error: str
    error_type: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str = ""
