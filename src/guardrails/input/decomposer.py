"""
src/guardrails/input/decomposer.py
───────────────────────────────────
Query decomposition: uses a cheap LLM call to split complex multi-part 
questions into atomic sub-questions for better retrieval coverage.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.core.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DecompositionResult:
    """Result of query decomposition."""
    original_query: str
    sub_questions: list[str]
    was_decomposed: bool

    @property
    def primary_query(self) -> str:
        """Return the first sub-question or the original query."""
        return self.sub_questions[0] if self.sub_questions else self.original_query


_DECOMPOSER_PROMPT = """You are a query decomposition expert for a RAG system.

Given a complex user question, break it down into 2-4 simple, atomic sub-questions 
that together cover all aspects of the original question. Each sub-question should 
be independently searchable.

Rules:
- Only decompose if the question is genuinely complex (multiple distinct topics/entities).
- If the question is already simple and focused, return it as-is in a single-item list.
- Do not rephrase; keep the same intent and terminology.
- Respond ONLY with a JSON array of strings. No other text.

Examples:
Input: "What are my open Jira tickets and any related Notion notes from this week?"
Output: ["What are my open Jira tickets from this week?", "What Notion notes are related to my Jira tickets this week?"]

Input: "What is the project status?"
Output: ["What is the project status?"]

Now decompose:
Query: {query}
Output:"""


class QueryDecomposer:
    """
    Decomposes complex queries into atomic sub-questions using an LLM.
    
    Only triggers decomposition when:
    - Decomposition is enabled in config
    - Query length exceeds min_query_length
    - Query contains complexity indicators (multiple questions, 'and', 'also', etc.)
    """

    COMPLEXITY_SIGNALS = [
        r"\band\b.*\?",             # "X and Y?" pattern
        r"\?.*\band\b",             # "X? and Y" pattern
        r"\balso\b",
        r"\badditionally\b",
        r"\bmoreover\b",
        r"\bbesides\b",
        r"\bfurthermore\b",
        r"(?:.*\?){2,}",            # Multiple question marks
        r"\b(?:list|summarize|compare|contrast)\b.*\b(?:and|with)\b",
    ]

    def __init__(
        self,
        enabled: bool = True,
        max_sub_questions: int = 4,
        min_query_length: int = 80,
    ) -> None:
        self.enabled = enabled
        self.max_sub_questions = max_sub_questions
        self.min_query_length = min_query_length
        self._complexity_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.COMPLEXITY_SIGNALS
        ]

    def _is_complex(self, query: str) -> bool:
        """Heuristic check for query complexity."""
        if len(query) < self.min_query_length:
            return False
        return any(p.search(query) for p in self._complexity_patterns)

    def _call_llm(self, query: str) -> list[str]:
        """Call the LLM to decompose the query."""
        settings = get_settings()

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

            response = llm.invoke(_DECOMPOSER_PROMPT.format(query=query))
            content = response.content.strip()

            # Strip markdown code fences if present
            content = re.sub(r"```(?:json)?\s*|\s*```", "", content).strip()

            # Parse JSON array
            sub_questions = json.loads(content)

            if not isinstance(sub_questions, list):
                raise ValueError("Expected a JSON array")

            # Sanitize: ensure strings, cap at max
            cleaned = [
                str(q).strip()
                for q in sub_questions
                if str(q).strip()
            ]
            return cleaned[: self.max_sub_questions]

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse decomposer JSON response", extra={"error": str(e)})
            return [query]
        except Exception as e:
            logger.warning("Decomposer LLM call failed", extra={"error": str(e)})
            return [query]

    def decompose(self, query: str) -> DecompositionResult:
        """
        Decompose the query into sub-questions if complex.

        Args:
            query: The user's input query.

        Returns:
            DecompositionResult with original query and list of sub-questions.
        """
        if not self.enabled:
            return DecompositionResult(
                original_query=query,
                sub_questions=[query],
                was_decomposed=False,
            )

        if not self._is_complex(query):
            logger.debug("Query deemed simple, skipping decomposition")
            return DecompositionResult(
                original_query=query,
                sub_questions=[query],
                was_decomposed=False,
            )

        logger.info("Decomposing complex query", extra={"query": query[:100]})
        sub_questions = self._call_llm(query)

        was_decomposed = len(sub_questions) > 1 or (
            len(sub_questions) == 1 and sub_questions[0] != query
        )

        logger.info(
            "Query decomposed",
            extra={"num_sub_questions": len(sub_questions), "was_decomposed": was_decomposed},
        )

        return DecompositionResult(
            original_query=query,
            sub_questions=sub_questions,
            was_decomposed=was_decomposed,
        )
