"""
src/core/exceptions.py
──────────────────────
Domain-specific exception hierarchy for the Agentic RAG system.
All custom exceptions should inherit from AgenticRAGError.
"""
from __future__ import annotations


class AgenticRAGError(Exception):
    """Base exception for all Agentic RAG errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, details={self.details})"


# ── Guardrail Exceptions ──────────────────────────────────────────────────────

class GuardrailError(AgenticRAGError):
    """Base for all guardrail violations."""


class InjectionDetectedError(GuardrailError):
    """Raised when a prompt injection attack is detected in user input."""

    def __init__(self, trigger: str, method: str = "regex") -> None:
        super().__init__(
            message=f"Prompt injection detected via {method}: '{trigger}'",
            details={"trigger": trigger, "detection_method": method},
        )
        self.trigger = trigger
        self.method = method


class PIIDetectedError(GuardrailError):
    """Raised when PII is detected in the output with score above threshold."""

    def __init__(self, entities: list[dict], location: str = "output") -> None:
        super().__init__(
            message=f"PII detected in {location}: {[e.get('entity_type') for e in entities]}",
            details={"entities": entities, "location": location},
        )
        self.entities = entities
        self.location = location


class GroundingError(GuardrailError):
    """
    Raised when the generated answer contains statements not grounded
    in the retrieved context documents.
    """

    def __init__(self, ungrounded_ratio: float, threshold: float) -> None:
        super().__init__(
            message=(
                f"Grounding validation failed: {ungrounded_ratio:.1%} of answer is ungrounded "
                f"(threshold: {threshold:.1%})"
            ),
            details={
                "ungrounded_ratio": ungrounded_ratio,
                "threshold": threshold,
            },
        )
        self.ungrounded_ratio = ungrounded_ratio
        self.threshold = threshold


class ContentSafetyError(GuardrailError):
    """Raised when generated content violates content safety policies."""

    def __init__(self, category: str, score: float) -> None:
        super().__init__(
            message=f"Content safety violation: category='{category}', score={score:.2f}",
            details={"category": category, "score": score},
        )
        self.category = category
        self.score = score


# ── Agent Exceptions ──────────────────────────────────────────────────────────

class AgentError(AgenticRAGError):
    """Base for agent execution errors."""


class MaxIterationsExceededError(AgentError):
    """Raised when the agent exceeds its maximum iteration count."""

    def __init__(self, max_iterations: int) -> None:
        super().__init__(
            message=f"Agent exceeded maximum iterations ({max_iterations})",
            details={"max_iterations": max_iterations},
        )


class RetrievalError(AgentError):
    """Raised when document retrieval fails."""

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            message=f"Retrieval failed for query '{query}': {reason}",
            details={"query": query, "reason": reason},
        )


# ── Infrastructure Exceptions ─────────────────────────────────────────────────

class VectorStoreError(AgenticRAGError):
    """Raised on Qdrant client errors."""


class CacheError(AgenticRAGError):
    """Raised on Redis client errors."""


class ConnectorError(AgenticRAGError):
    """Raised when a data connector (Gmail/Notion/Jira) fails."""

    def __init__(self, connector_name: str, reason: str) -> None:
        super().__init__(
            message=f"Connector '{connector_name}' failed: {reason}",
            details={"connector": connector_name, "reason": reason},
        )


class LLMClientError(AgenticRAGError):
    """Raised when the LLM API call fails."""
