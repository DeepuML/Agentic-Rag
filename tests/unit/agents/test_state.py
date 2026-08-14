"""
tests/unit/agents/test_state.py
────────────────────────────────
Unit tests for agent state creation and structure.
"""
import pytest
from src.agents.state import AgentState, create_initial_state


class TestAgentState:

    def test_create_initial_state_defaults(self):
        state = create_initial_state(
            query="What are my open tickets?",
            user_id="user_1",
            session_id="session_1",
        )

        assert state["query"] == "What are my open tickets?"
        assert state["original_query"] == "What are my open tickets?"
        assert state["user_id"] == "user_1"
        assert state["session_id"] == "session_1"
        assert state["iterations"] == 0
        assert state["max_iterations"] == 3
        assert state["is_sufficient"] is False
        assert state["context_docs"] == []
        assert state["all_docs"] == []
        assert state["sub_questions"] == []
        assert state["answer"] == ""
        assert state["plan"] == ""
        assert state["error"] is None
        assert state["messages"] == []
        assert state["guardrail_flags"] == {}
        assert state["metadata"] == {}

    def test_create_initial_state_with_sub_questions(self):
        state = create_initial_state(
            query="What are my tickets and roadmap items?",
            user_id="user_1",
            session_id="session_1",
            sub_questions=["What are my tickets?", "What are the roadmap items?"],
            max_iterations=5,
        )

        assert len(state["sub_questions"]) == 2
        assert state["max_iterations"] == 5

    def test_state_has_all_required_keys(self):
        required_keys = [
            "messages", "query", "original_query", "sub_questions",
            "context_docs", "all_docs", "is_sufficient", "iterations",
            "max_iterations", "plan", "answer", "user_id", "session_id",
            "guardrail_flags", "error", "metadata",
        ]
        state = create_initial_state("test", "u1", "s1")
        for key in required_keys:
            assert key in state, f"Missing key: {key}"
