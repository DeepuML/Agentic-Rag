"""
src/guardrails/output/grounding_validator.py
────────────────────────────────────────────
Validates that the generated answer is grounded in the retrieved context documents.
Raises GroundingError if too many claims are not supported by source documents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document

from src.core.config import get_settings
from src.core.exceptions import GroundingError
from src.utils.helpers import extract_sentences
from src.utils.logger import get_logger
from src.utils.metrics import GROUNDING_FAILURES, GUARDRAIL_TRIGGERS

logger = get_logger(__name__)


@dataclass
class GroundingResult:
    """Result of grounding validation."""
    is_grounded: bool
    grounding_score: float          # 0.0 (ungrounded) to 1.0 (fully grounded)
    ungrounded_ratio: float
    grounded_sentences: int
    total_sentences: int
    ungrounded_examples: list[str]  # Examples of ungrounded claims


class GroundingValidator:
    """
    Validates that the generated answer is grounded in retrieved documents.

    Strategy:
      1. Split the answer into individual sentences.
      2. For each sentence, check if it is semantically or lexically 
         supported by at least one context document.
      3. If the ratio of ungrounded sentences exceeds the threshold,
         raise a GroundingError (in strict mode).

    Two validation modes:
      - lexical: Fast n-gram/keyword overlap check (default for short answers)
      - semantic: Use embedding similarity for deeper grounding (optional)
    """

    REFUSAL_SUFFIXES_THAT_ARE_OK = {
        "I cannot",
        "I don't have",
        "I don't know",
        "Based on the provided",
        "According to",
        "The context does not",
        "No information",
        "I was unable",
    }

    def __init__(
        self,
        strict_mode: bool | None = None,
        max_ungrounded_ratio: float = 0.20,
        similarity_threshold: float = 0.70,
    ) -> None:
        settings = get_settings()
        self.strict_mode = strict_mode if strict_mode is not None else settings.grounding_strict_mode
        self.max_ungrounded_ratio = max_ungrounded_ratio
        self.similarity_threshold = similarity_threshold

    def _is_trivial_sentence(self, sentence: str) -> bool:
        """
        Returns True for sentences that don't need grounding:
        - Very short sentences (< 5 words)
        - Sentences expressing uncertainty / inability
        - Transition phrases
        """
        words = sentence.split()
        if len(words) < 5:
            return True
        lowered = sentence.lower()
        return any(suffix.lower() in lowered for suffix in self.REFUSAL_SUFFIXES_THAT_ARE_OK)

    def _lexical_grounding_check(self, sentence: str, context_docs: list[Document]) -> bool:
        """
        Check if a sentence is lexically grounded in context docs
        using word overlap (Jaccard-like similarity).
        """
        # Extract meaningful words from the sentence (skip stopwords)
        STOPWORDS = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "shall", "can", "to", "of", "in", "for",
            "on", "with", "at", "by", "from", "as", "into", "through", "and",
            "but", "or", "so", "if", "this", "that", "these", "those", "it",
            "its", "their", "they", "he", "she", "we", "you", "i",
        }

        sentence_words = {
            w.lower().strip(".,!?;:'\"()")
            for w in sentence.split()
            if w.lower() not in STOPWORDS and len(w) > 2
        }

        if not sentence_words:
            return True  # Treat empty word set as grounded

        # Build word set from all context documents
        all_context_words: set[str] = set()
        for doc in context_docs:
            doc_words = {
                w.lower().strip(".,!?;:'\"()")
                for w in doc.page_content.split()
                if w.lower() not in STOPWORDS and len(w) > 2
            }
            all_context_words.update(doc_words)

        if not all_context_words:
            return False

        # Jaccard overlap
        intersection = sentence_words & all_context_words
        overlap_ratio = len(intersection) / len(sentence_words)

        return overlap_ratio >= self.similarity_threshold

    def validate(
        self,
        answer: str,
        context_docs: list[Document],
        raise_on_failure: bool | None = None,
    ) -> GroundingResult:
        """
        Validate that the answer is grounded in context_docs.

        Args:
            answer: The generated answer text.
            context_docs: Retrieved documents used to generate the answer.
            raise_on_failure: Override strict_mode for this call.

        Returns:
            GroundingResult with grounding score and analysis.

        Raises:
            GroundingError: If strict mode is enabled and grounding fails.
        """
        should_raise = raise_on_failure if raise_on_failure is not None else self.strict_mode

        if not context_docs:
            logger.warning("No context docs provided for grounding validation")
            # If no docs, we can't validate — pass through unless strict
            if should_raise and self.strict_mode:
                raise GroundingError(
                    ungrounded_ratio=1.0,
                    threshold=self.max_ungrounded_ratio,
                )
            return GroundingResult(
                is_grounded=False,
                grounding_score=0.0,
                ungrounded_ratio=1.0,
                grounded_sentences=0,
                total_sentences=0,
                ungrounded_examples=[],
            )

        sentences = extract_sentences(answer)
        if not sentences:
            return GroundingResult(
                is_grounded=True,
                grounding_score=1.0,
                ungrounded_ratio=0.0,
                grounded_sentences=0,
                total_sentences=0,
                ungrounded_examples=[],
            )

        grounded_count = 0
        ungrounded_examples: list[str] = []

        for sentence in sentences:
            if self._is_trivial_sentence(sentence):
                grounded_count += 1
                continue

            is_grounded = self._lexical_grounding_check(sentence, context_docs)
            if is_grounded:
                grounded_count += 1
            else:
                ungrounded_examples.append(sentence[:120])

        total = len(sentences)
        ungrounded_count = total - grounded_count
        ungrounded_ratio = ungrounded_count / total if total > 0 else 0.0
        grounding_score = grounded_count / total if total > 0 else 1.0
        is_grounded = ungrounded_ratio <= self.max_ungrounded_ratio

        logger.info(
            "Grounding validation complete",
            extra={
                "is_grounded": is_grounded,
                "grounding_score": grounding_score,
                "ungrounded_ratio": ungrounded_ratio,
                "total_sentences": total,
            },
        )

        if not is_grounded:
            GROUNDING_FAILURES.inc()
            GUARDRAIL_TRIGGERS.labels(guardrail_type="grounding", direction="output").inc()

            if should_raise:
                raise GroundingError(
                    ungrounded_ratio=ungrounded_ratio,
                    threshold=self.max_ungrounded_ratio,
                )

        return GroundingResult(
            is_grounded=is_grounded,
            grounding_score=grounding_score,
            ungrounded_ratio=ungrounded_ratio,
            grounded_sentences=grounded_count,
            total_sentences=total,
            ungrounded_examples=ungrounded_examples[:3],
        )
