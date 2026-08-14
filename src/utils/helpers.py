"""
src/utils/helpers.py
────────────────────
Shared utility functions used across the application.
"""
from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from contextlib import contextmanager
from typing import Any, Generator


# ── Text Utilities ────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Normalize unicode, collapse whitespace, and strip edges."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate_text(text: str, max_chars: int = 500, suffix: str = "...") -> str:
    """Truncate text to max_chars, appending suffix if truncated."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(suffix)] + suffix


def extract_sentences(text: str) -> list[str]:
    """Simple sentence splitter based on punctuation."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def compute_content_hash(content: str) -> str:
    """Compute a stable SHA-256 hash for deduplication."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sanitize_for_log(text: str, max_len: int = 200) -> str:
    """Sanitize text for safe logging (truncate + strip newlines)."""
    clean = text.replace("\n", " ").replace("\r", "")
    return truncate_text(clean, max_len)


# ── ID Utilities ──────────────────────────────────────────────────────────────

def make_session_key(user_id: str, session_id: str) -> str:
    """Generate a consistent Redis key for a session."""
    return f"session:{user_id}:{session_id}:history"


def make_memory_key(user_id: str) -> str:
    """Generate a consistent key for long-term user memory."""
    return f"memory:{user_id}"


# ── Timing Utilities ──────────────────────────────────────────────────────────

@contextmanager
def timer() -> Generator[dict[str, float], None, None]:
    """Context manager that records elapsed time in milliseconds."""
    result: dict[str, float] = {}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["elapsed_ms"] = (time.perf_counter() - start) * 1000


# ── Dict Utilities ────────────────────────────────────────────────────────────

def flatten_dict(d: dict[str, Any], prefix: str = "", sep: str = ".") -> dict[str, Any]:
    """Recursively flatten a nested dict."""
    items: dict[str, Any] = {}
    for k, v in d.items():
        new_key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep))
        else:
            items[new_key] = v
    return items


def safe_get(d: dict, *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dict with a chain of keys."""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


# ── Validation Utilities ──────────────────────────────────────────────────────

def is_valid_user_id(user_id: str) -> bool:
    """Validate that a user_id is alphanumeric with optional hyphens/underscores."""
    return bool(re.match(r"^[a-zA-Z0-9_\-]{1,64}$", user_id))


def is_valid_session_id(session_id: str) -> bool:
    """Validate session_id format."""
    return bool(re.match(r"^[a-zA-Z0-9_\-]{1,128}$", session_id))
