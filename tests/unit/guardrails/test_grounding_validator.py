"""
tests/unit/guardrails/test_grounding_validator.py
──────────────────────────────────────────────────
Unit tests for the grounding validator.
"""
import pytest
from langchain_core.documents import Document

from src.guardrails.output.grounding_validator import GroundingValidator
from src.core.exceptions import GroundingError


@pytest.fixture
def validator():
    return GroundingValidator(strict_mode=False, max_ungrounded_ratio=0.20)


@pytest.fixture
def context_docs():
    return [
        Document(
            page_content="Alex Chen is working on the Qdrant vector search implementation for PROJ-101.",
            metadata={"source": "jira", "source_id": "jira_001"},
        ),
        Document(
            page_content="The Q3 roadmap includes semantic search with 40% relevancy improvement target.",
            metadata={"source": "notion", "source_id": "notion_001"},
        ),
        Document(
            page_content="Production incident on July 26 caused 47 minutes of API latency spike.",
            metadata={"source": "gmail", "source_id": "gmail_001"},
        ),
    ]


class TestGroundingValidator:

    def test_grounded_answer_passes(self, validator, context_docs):
        answer = (
            "Alex Chen is working on the Qdrant vector search implementation. "
            "The Q3 roadmap targets a 40% relevancy improvement with semantic search."
        )
        result = validator.validate(answer, context_docs)
        assert result.is_grounded is True
        assert result.grounding_score > 0.5

    def test_empty_answer_passes(self, validator, context_docs):
        result = validator.validate("", context_docs)
        assert result.is_grounded is True

    def test_no_context_docs(self, validator):
        answer = "This is an answer with no context documents."
        result = validator.validate(answer, [])
        assert result.is_grounded is False

    def test_trivial_sentences_are_grounded(self, validator, context_docs):
        answer = "I cannot provide more information. Based on the provided documents."
        result = validator.validate(answer, context_docs)
        assert result.is_grounded is True

    def test_grounding_score_range(self, validator, context_docs):
        answer = "The search is implemented by Alex. Q3 targets are set."
        result = validator.validate(answer, context_docs)
        assert 0.0 <= result.grounding_score <= 1.0
        assert 0.0 <= result.ungrounded_ratio <= 1.0

    def test_strict_mode_raises_on_failure(self, context_docs):
        strict_validator = GroundingValidator(strict_mode=True, max_ungrounded_ratio=0.01)
        # Completely unrelated answer should fail
        answer = (
            "The quantum mechanics of superconducting materials involves Cooper pairs "
            "and BCS theory with phonon-mediated electron interactions."
        )
        with pytest.raises(GroundingError):
            strict_validator.validate(answer, context_docs, raise_on_failure=True)

    def test_result_has_required_fields(self, validator, context_docs):
        result = validator.validate("Alex is working on the search feature.", context_docs)
        assert hasattr(result, "is_grounded")
        assert hasattr(result, "grounding_score")
        assert hasattr(result, "ungrounded_ratio")
        assert hasattr(result, "grounded_sentences")
        assert hasattr(result, "total_sentences")
        assert hasattr(result, "ungrounded_examples")
