"""
src/agents/state.py
───────────────────
AgentState TypedDict definition for the LangGraph StateGraph.
This is the shared state object passed between all agent nodes.
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    Central state object for the Agentic RAG graph.

    Fields:
        messages:        Chat history accumulator (uses LangGraph's add_messages reducer).
        query:           The current (possibly reformulated) query string.
        original_query:  The unmodified user query (preserved for evaluation).
        sub_questions:   Decomposed sub-questions from the decomposer guardrail.
        context_docs:    Documents retrieved from Qdrant for the current iteration.
        all_docs:        Accumulated documents across all retrieval iterations.
        is_sufficient:   Whether the retriever has found adequate context.
        iterations:      Number of times the retrieve → evaluate loop has run.
        max_iterations:  Maximum allowed iterations before forced generation.
        plan:            The planner's strategy description.
        answer:          The final generated answer text.
        user_id:         The requesting user's ID (for memory lookups).
        session_id:      The current conversation session ID.
        guardrail_flags: Dict of flags set by input/output guardrails.
        error:           Optional error message if a node fails gracefully.
        metadata:        Arbitrary metadata bag for tracing and evaluation.
    """

    # ── Core Message History ─────────────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Query Management ─────────────────────────────────────────────────────
    query: str
    original_query: str
    sub_questions: list[str]

    # ── Retrieval ────────────────────────────────────────────────────────────
    context_docs: list[Document]
    all_docs: list[Document]
    is_sufficient: bool
    iterations: int
    max_iterations: int
    plan: str

    # ── Output ───────────────────────────────────────────────────────────────
    answer: str

    # ── Request Context ──────────────────────────────────────────────────────
    user_id: str
    session_id: str

    # ── Observability ────────────────────────────────────────────────────────
    guardrail_flags: dict[str, Any]
    error: str | None
    metadata: dict[str, Any]


def create_initial_state(
    query: str,
    user_id: str,
    session_id: str,
    sub_questions: list[str] | None = None,
    max_iterations: int = 3,
) -> AgentState:
    """
    Factory function to create a clean initial AgentState
    for a new chat request.
    """
    return AgentState(
        messages=[],
        query=query,
        original_query=query,
        sub_questions=sub_questions or [],
        context_docs=[],
        all_docs=[],
        is_sufficient=False,
        iterations=0,
        max_iterations=max_iterations,
        plan="",
        answer="",
        user_id=user_id,
        session_id=session_id,
        guardrail_flags={},
        error=None,
        metadata={},
    )
