"""
src/memory/short_term.py
────────────────────────
Redis-backed short-term conversation memory.
Stores the last N conversation turns per session using a Redis list.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict

import redis

from src.core.config import get_settings
from src.core.exceptions import CacheError
from src.utils.helpers import make_session_key
from src.utils.logger import get_logger
from src.utils.metrics import MEMORY_OPS

logger = get_logger(__name__)


@dataclass
class ConversationTurn:
    """A single conversation turn (user + assistant pair)."""
    role: str           # "user" or "assistant"
    content: str
    timestamp: str = ""
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ShortTermMemory:
    """
    Redis-backed short-term memory storing the last N conversation turns.

    Data structure:
        Redis key: session:{user_id}:{session_id}:history
        Redis type: List (LPUSH + LTRIM for capped history)
        Serialization: JSON

    Each list element is a JSON-serialized ConversationTurn.
    Newest entries are at index 0 (LPUSH).
    """

    def __init__(
        self,
        max_turns: int | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.max_turns = max_turns or settings.short_term_memory_turns
        self.ttl_seconds = ttl_seconds or settings.redis_ttl_seconds
        self._client: redis.Redis | None = None

    def _get_client(self) -> redis.Redis:
        """Lazy-initialize Redis client."""
        if self._client is None:
            settings = get_settings()
            try:
                self._client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    password=settings.redis_password or None,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                self._client.ping()
                logger.info("Redis short-term memory client connected")
            except redis.ConnectionError as e:
                raise CacheError(f"Cannot connect to Redis: {e}") from e
        return self._client

    def add_turn(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """
        Append a turn to the conversation history.
        Automatically trims the list to max_turns * 2 entries (user + assistant).
        """
        import arrow

        client = self._get_client()
        key = make_session_key(user_id, session_id)

        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=arrow.utcnow().isoformat(),
            metadata=metadata or {},
        )

        try:
            pipe = client.pipeline()
            pipe.lpush(key, json.dumps(asdict(turn)))
            # Keep max_turns * 2 entries (each turn has user + assistant messages)
            pipe.ltrim(key, 0, self.max_turns * 2 - 1)
            pipe.expire(key, self.ttl_seconds)
            pipe.execute()

            MEMORY_OPS.labels(memory_type="short_term", operation="write").inc()
            logger.debug("Short-term memory turn added", extra={"key": key, "role": role})

        except redis.RedisError as e:
            logger.error("Failed to add turn to short-term memory", extra={"error": str(e)})
            raise CacheError(f"Redis write failed: {e}") from e

    def get_history(
        self,
        user_id: str,
        session_id: str,
        last_n: int | None = None,
    ) -> list[ConversationTurn]:
        """
        Retrieve conversation history in chronological order (oldest first).

        Args:
            user_id: User identifier.
            session_id: Session identifier.
            last_n: Return at most last_n turns. Defaults to max_turns.

        Returns:
            List of ConversationTurn objects (oldest → newest).
        """
        client = self._get_client()
        key = make_session_key(user_id, session_id)
        n = last_n or self.max_turns * 2

        try:
            raw_entries = client.lrange(key, 0, n - 1)
            MEMORY_OPS.labels(memory_type="short_term", operation="read").inc()
        except redis.RedisError as e:
            logger.error("Failed to read short-term memory", extra={"error": str(e)})
            return []

        turns: list[ConversationTurn] = []
        for entry in reversed(raw_entries):  # reverse to get chronological order
            try:
                data = json.loads(entry)
                turns.append(ConversationTurn(**data))
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Failed to deserialize memory entry", extra={"error": str(e)})

        return turns

    def get_formatted_history(self, user_id: str, session_id: str) -> str:
        """Return conversation history as a formatted string for LLM context."""
        turns = self.get_history(user_id, session_id)
        if not turns:
            return ""

        lines = []
        for turn in turns:
            prefix = "User" if turn.role == "user" else "Assistant"
            lines.append(f"{prefix}: {turn.content}")
        return "\n".join(lines)

    def clear_session(self, user_id: str, session_id: str) -> bool:
        """Delete all memory for a specific session."""
        client = self._get_client()
        key = make_session_key(user_id, session_id)
        try:
            deleted = client.delete(key)
            logger.info("Short-term memory cleared", extra={"key": key})
            return bool(deleted)
        except redis.RedisError as e:
            logger.error("Failed to clear session memory", extra={"error": str(e)})
            return False

    def clear_all_sessions(self, user_id: str) -> int:
        """Delete all session memories for a user."""
        client = self._get_client()
        pattern = f"session:{user_id}:*:history"
        try:
            keys = client.keys(pattern)
            if keys:
                return client.delete(*keys)
            return 0
        except redis.RedisError as e:
            logger.error("Failed to clear all sessions", extra={"error": str(e)})
            return 0

    def ping(self) -> bool:
        """Check if Redis is reachable."""
        try:
            return self._get_client().ping()
        except Exception:
            return False
