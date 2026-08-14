"""
src/agents/tools.py
───────────────────
LangChain tools wrapping Qdrant retrieval and other agent capabilities.
These tools are available to the agent nodes during execution.
"""
from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.tools import tool

from src.core.config import get_settings
from src.core.vector_store import QdrantVectorStore
from src.utils.logger import get_logger
from src.utils.metrics import RETRIEVAL_LATENCY, DOCS_RETRIEVED
import time

logger = get_logger(__name__)
_vector_store: QdrantVectorStore | None = None


def get_vector_store() -> QdrantVectorStore:
    """Return the module-level singleton vector store."""
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore()
    return _vector_store


@tool
def retrieve_documents(query: str, k: int = 5, score_threshold: float = 0.5) -> list[dict]:
    """
    Retrieve the most relevant documents from the Qdrant vector store
    for the given query.

    Args:
        query: The search query string.
        k: Number of top documents to retrieve (default: 5).
        score_threshold: Minimum similarity score (0-1, default: 0.5).

    Returns:
        A list of document dicts with 'content' and 'metadata' keys.
    """
    start = time.perf_counter()
    vs = get_vector_store()

    docs = vs.similarity_search(query=query, k=k, score_threshold=score_threshold)

    elapsed = time.perf_counter() - start
    RETRIEVAL_LATENCY.observe(elapsed)
    DOCS_RETRIEVED.observe(len(docs))

    logger.debug("Tool: retrieve_documents", extra={"query": query[:60], "results": len(docs)})

    return [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": doc.metadata.get("_score", 0.0),
        }
        for doc in docs
    ]


@tool
def retrieve_with_filter(
    query: str,
    source_type: str,
    k: int = 5,
) -> list[dict]:
    """
    Retrieve documents filtered by source type (e.g., 'gmail', 'notion', 'jira').

    Args:
        query: The search query string.
        source_type: The data source to filter by ('gmail', 'notion', 'jira').
        k: Number of top documents to retrieve.

    Returns:
        A list of filtered document dicts.
    """
    vs = get_vector_store()
    docs = vs.similarity_search(
        query=query,
        k=k,
        filter_conditions={"source": source_type},
    )
    logger.debug(
        "Tool: retrieve_with_filter",
        extra={"query": query[:60], "source_type": source_type, "results": len(docs)},
    )
    return [
        {"content": doc.page_content, "metadata": doc.metadata}
        for doc in docs
    ]


@tool
def get_collection_stats() -> dict[str, Any]:
    """
    Return statistics about the main document collection in Qdrant.
    Useful for the planner to understand available data.

    Returns:
        Dict with 'points_count', 'status', and 'vectors_count'.
    """
    vs = get_vector_store()
    settings = get_settings()
    try:
        info = vs.collection_info(settings.qdrant_collection_name)
        return info
    except Exception as e:
        logger.warning("Could not get collection stats", extra={"error": str(e)})
        return {"error": str(e), "points_count": 0}


# ── Tool Registry ─────────────────────────────────────────────────────────────

ALL_TOOLS = [retrieve_documents, retrieve_with_filter, get_collection_stats]

TOOLS_BY_NAME: dict[str, Any] = {t.name: t for t in ALL_TOOLS}
