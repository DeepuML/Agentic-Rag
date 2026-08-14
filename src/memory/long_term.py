"""
src/memory/long_term.py
───────────────────────
Qdrant-backed long-term user memory.
Stores user preferences, interaction summaries, and learned context
as vector embeddings for semantic retrieval.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict, field
from typing import Any

from langchain_core.documents import Document

from src.core.config import get_settings
from src.core.vector_store import QdrantVectorStore
from src.utils.logger import get_logger
from src.utils.metrics import MEMORY_OPS

logger = get_logger(__name__)


@dataclass
class MemoryEntry:
    """A long-term memory entry for a user."""
    user_id: str
    content: str
    memory_type: str  # "preference" | "summary" | "fact" | "feedback"
    source_session_id: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class LongTermMemory:
    """
    Qdrant-backed long-term memory that stores user-specific context
    as vector embeddings for semantic retrieval.

    Use cases:
      - "User prefers technical summaries" → preference
      - "User is working on Project X" → fact
      - "Previous session discussed Q3 OKRs" → summary
      - "User gave negative feedback on verbose answers" → feedback
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.collection = settings.qdrant_memory_collection
        self._vs = QdrantVectorStore(settings)

    def _ensure_collection(self) -> None:
        """Ensure the memory collection exists in Qdrant."""
        self._vs.ensure_collection(self.collection)

    def store_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "fact",
        session_id: str = "",
        tags: list[str] | None = None,
    ) -> str:
        """
        Store a new memory entry for a user.

        Args:
            user_id: The user's ID.
            content: The memory content to store.
            memory_type: Type of memory ('preference', 'summary', 'fact', 'feedback').
            session_id: Source session ID.
            tags: Optional tags for filtering.

        Returns:
            The memory entry's unique ID.
        """
        import arrow

        self._ensure_collection()

        entry = MemoryEntry(
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            source_session_id=session_id,
            tags=tags or [],
            created_at=arrow.utcnow().isoformat(),
        )

        doc = Document(
            page_content=content,
            metadata={
                "user_id": user_id,
                "memory_id": entry.id,
                "memory_type": memory_type,
                "source_session_id": session_id,
                "tags": ",".join(tags or []),
                "created_at": entry.created_at,
                "source": "long_term_memory",
            },
        )

        self._vs.upsert_documents([doc], collection_name=self.collection)
        MEMORY_OPS.labels(memory_type="long_term", operation="write").inc()

        logger.info(
            "Long-term memory stored",
            extra={
                "user_id": user_id,
                "memory_type": memory_type,
                "memory_id": entry.id,
            },
        )
        return entry.id

    def retrieve_memories(
        self,
        user_id: str,
        query: str,
        k: int = 3,
        memory_type: str | None = None,
    ) -> list[Document]:
        """
        Retrieve relevant memories for a user using semantic search.

        Args:
            user_id: User whose memories to search.
            query: Semantic query for memory retrieval.
            k: Max number of memories to return.
            memory_type: Optional filter by memory type.

        Returns:
            List of relevant Document objects.
        """
        self._ensure_collection()

        filter_conditions: dict[str, Any] = {"user_id": user_id}
        if memory_type:
            filter_conditions["memory_type"] = memory_type

        docs = self._vs.similarity_search(
            query=query,
            k=k,
            collection_name=self.collection,
            score_threshold=0.40,
            filter_conditions=filter_conditions,
        )

        MEMORY_OPS.labels(memory_type="long_term", operation="read").inc()

        logger.debug(
            "Long-term memories retrieved",
            extra={"user_id": user_id, "query": query[:50], "count": len(docs)},
        )
        return docs

    def get_user_preferences(self, user_id: str, context: str = "") -> str:
        """
        Retrieve user preferences as a formatted string for LLM context injection.

        Args:
            user_id: User ID.
            context: Optional context to find relevant preferences.

        Returns:
            Formatted string of user preferences.
        """
        query = context or f"user preferences for {user_id}"
        docs = self.retrieve_memories(
            user_id=user_id,
            query=query,
            k=5,
            memory_type="preference",
        )

        if not docs:
            return ""

        prefs = [f"- {doc.page_content}" for doc in docs]
        return "User preferences:\n" + "\n".join(prefs)

    def delete_user_memories(self, user_id: str) -> int:
        """Delete all memories for a user."""
        try:
            deleted = self._vs.delete_by_metadata(
                filter_conditions={"user_id": user_id},
                collection_name=self.collection,
            )
            logger.info("Long-term memories deleted", extra={"user_id": user_id})
            return deleted
        except Exception as e:
            logger.error("Failed to delete user memories", extra={"error": str(e)})
            return 0

    def summarize_session_to_memory(
        self,
        user_id: str,
        session_id: str,
        conversation_history: str,
    ) -> str | None:
        """
        Use LLM to extract key facts and preferences from a session,
        then store them as long-term memories.

        Returns:
            Memory ID if stored, None if nothing notable extracted.
        """
        settings = get_settings()

        SUMMARY_PROMPT = """Analyze this conversation and extract:
1. User preferences (how they like information presented)
2. Key facts mentioned about the user's context (projects, role, etc.)

Respond with a single concise paragraph summarizing these insights.
If there's nothing notable to remember, respond with "NOTHING_TO_STORE".

Conversation:
{history}

Summary:"""

        try:
            if settings.llm_provider == "openai":
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(
                    model=settings.openai_model,
                    temperature=0.0,
                    api_key=settings.openai_api_key,
                )
            else:
                from langchain_google_genai import ChatGoogleGenerativeAI
                llm = ChatGoogleGenerativeAI(
                    model=settings.gemini_model,
                    temperature=0.0,
                    google_api_key=settings.gemini_api_key,
                )

            response = llm.invoke(SUMMARY_PROMPT.format(history=conversation_history[:3000]))
            summary = response.content.strip()

            if "NOTHING_TO_STORE" in summary:
                return None

            memory_id = self.store_memory(
                user_id=user_id,
                content=summary,
                memory_type="summary",
                session_id=session_id,
            )
            return memory_id

        except Exception as e:
            logger.warning("Failed to summarize session to memory", extra={"error": str(e)})
            return None
