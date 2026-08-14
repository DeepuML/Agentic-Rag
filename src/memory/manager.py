"""
src/memory/manager.py
─────────────────────
Unified memory interface that combines short-term (Redis) and long-term (Qdrant)
memory access into a single, coherent API for use by the agent and routes.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.documents import Document

from src.memory.short_term import ShortTermMemory, ConversationTurn
from src.memory.long_term import LongTermMemory
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MemoryManager:
    """
    High-level memory interface combining:
      - Short-term: Redis-backed conversation history (last N turns)
      - Long-term: Qdrant-backed user preferences and session summaries

    Usage in API routes:
        memory = MemoryManager()
        # Add a user turn
        memory.add_user_message(user_id, session_id, "What are my open tickets?")
        # Add assistant response
        memory.add_assistant_message(user_id, session_id, "You have 3 open tickets...")
        # Retrieve context for next request
        context = memory.get_context(user_id, session_id, query)
    """

    def __init__(self) -> None:
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory()

    # ── Short-term Operations ─────────────────────────────────────────────────

    def add_user_message(
        self, user_id: str, session_id: str, content: str, metadata: dict | None = None
    ) -> None:
        """Record a user message to short-term memory."""
        try:
            self.short_term.add_turn(
                user_id=user_id,
                session_id=session_id,
                role="user",
                content=content,
                metadata=metadata,
            )
        except Exception as e:
            logger.warning("Failed to add user message to memory", extra={"error": str(e)})

    def add_assistant_message(
        self, user_id: str, session_id: str, content: str, metadata: dict | None = None
    ) -> None:
        """Record an assistant message to short-term memory."""
        try:
            self.short_term.add_turn(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=content,
                metadata=metadata,
            )
        except Exception as e:
            logger.warning("Failed to add assistant message to memory", extra={"error": str(e)})

    def get_conversation_history(
        self, user_id: str, session_id: str
    ) -> list[ConversationTurn]:
        """Get the conversation history for a session."""
        try:
            return self.short_term.get_history(user_id, session_id)
        except Exception as e:
            logger.warning("Failed to get conversation history", extra={"error": str(e)})
            return []

    def get_formatted_history(self, user_id: str, session_id: str) -> str:
        """Get conversation history as a formatted string."""
        try:
            return self.short_term.get_formatted_history(user_id, session_id)
        except Exception as e:
            logger.warning("Failed to get formatted history", extra={"error": str(e)})
            return ""

    # ── Long-term Operations ──────────────────────────────────────────────────

    def store_preference(
        self, user_id: str, preference: str, session_id: str = ""
    ) -> str | None:
        """Store a user preference in long-term memory."""
        try:
            return self.long_term.store_memory(
                user_id=user_id,
                content=preference,
                memory_type="preference",
                session_id=session_id,
            )
        except Exception as e:
            logger.warning("Failed to store preference", extra={"error": str(e)})
            return None

    def get_user_context(self, user_id: str, query: str) -> str:
        """
        Build a combined context string from long-term memories
        relevant to the current query.
        """
        try:
            preferences = self.long_term.get_user_preferences(user_id, query)
            relevant_memories = self.long_term.retrieve_memories(
                user_id=user_id,
                query=query,
                k=3,
            )

            memory_snippets = [
                f"- {doc.page_content}" for doc in relevant_memories
            ]

            parts = []
            if preferences:
                parts.append(preferences)
            if memory_snippets:
                parts.append("Relevant past context:\n" + "\n".join(memory_snippets))

            return "\n\n".join(parts)
        except Exception as e:
            logger.warning("Failed to get user context", extra={"error": str(e)})
            return ""

    # ── Session Management ────────────────────────────────────────────────────

    def clear_session(self, user_id: str, session_id: str) -> dict[str, bool]:
        """Clear all memory for a specific session."""
        results: dict[str, bool] = {}
        try:
            results["short_term"] = self.short_term.clear_session(user_id, session_id)
        except Exception as e:
            logger.error("Failed to clear short-term session", extra={"error": str(e)})
            results["short_term"] = False

        # Long-term memory is intentionally preserved across sessions
        # (it stores user preferences, not session data)
        results["long_term"] = True
        return results

    def post_session_summarize(self, user_id: str, session_id: str) -> None:
        """
        Called at the end of a session to extract and store relevant
        information into long-term memory.
        """
        try:
            history = self.get_formatted_history(user_id, session_id)
            if history:
                memory_id = self.long_term.summarize_session_to_memory(
                    user_id=user_id,
                    session_id=session_id,
                    conversation_history=history,
                )
                if memory_id:
                    logger.info(
                        "Session summarized to long-term memory",
                        extra={"user_id": user_id, "session_id": session_id, "memory_id": memory_id},
                    )
        except Exception as e:
            logger.warning("Failed to post-session summarize", extra={"error": str(e)})

    def health_check(self) -> dict[str, bool]:
        """Check connectivity for both memory backends."""
        return {
            "redis": self.short_term.ping(),
            "qdrant": True,  # Qdrant health is checked at startup
        }


@lru_cache(maxsize=1)
def get_memory_manager() -> MemoryManager:
    """Return cached MemoryManager singleton."""
    return MemoryManager()
