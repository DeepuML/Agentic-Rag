"""
src/agents/graph.py
───────────────────
LangGraph StateGraph compilation.
Wires the 5 nodes (planner, retriever, evaluator, reflector, generator)
with conditional edges implementing the Plan→Retrieve→Evaluate→Reflect→Generate loop.
"""
from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from src.agents.nodes import evaluator, generator, planner, reflector, retriever
from src.agents.state import AgentState
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Conditional Edge Functions ────────────────────────────────────────────────

def route_after_evaluation(
    state: AgentState,
) -> Literal["generator", "reflector"]:
    """
    Conditional routing after the evaluator node.

    - Routes to 'generator' if docs are sufficient OR max iterations reached.
    - Routes to 'reflector' if docs are insufficient and retries remain.
    """
    is_sufficient = state.get("is_sufficient", False)
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 3)

    if is_sufficient or iterations >= max_iterations:
        logger.debug(
            "Routing to generator",
            extra={"is_sufficient": is_sufficient, "iterations": iterations},
        )
        return "generator"

    logger.debug(
        "Routing to reflector",
        extra={"iterations": iterations, "max_iterations": max_iterations},
    )
    return "reflector"


# ── Graph Builder ─────────────────────────────────────────────────────────────

def build_rag_graph() -> StateGraph:
    """
    Construct and compile the LangGraph StateGraph for the Agentic RAG pipeline.

    Graph topology:
        START → planner → retriever → evaluator
                                          │
                           ┌─────────────┤
                    sufficient?          │ not sufficient
                           │             ▼
                           ▼         reflector → retriever (loop)
                       generator
                           │
                          END
    """
    graph = StateGraph(AgentState)

    # ── Register Nodes ───────────────────────────────────────────────────────
    graph.add_node("planner", planner)
    graph.add_node("retriever", retriever)
    graph.add_node("evaluator", evaluator)
    graph.add_node("reflector", reflector)
    graph.add_node("generator", generator)

    # ── Linear Edges ─────────────────────────────────────────────────────────
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "retriever")
    graph.add_edge("retriever", "evaluator")

    # ── Conditional Edge: evaluator → generator | reflector ──────────────────
    graph.add_conditional_edges(
        "evaluator",
        route_after_evaluation,
        {
            "generator": "generator",
            "reflector": "reflector",
        },
    )

    # ── Reflector loops back to retriever ────────────────────────────────────
    graph.add_edge("reflector", "retriever")

    # ── Terminal ──────────────────────────────────────────────────────────────
    graph.add_edge("generator", END)

    return graph


def compile_graph():
    """Compile and return the runnable LangGraph application."""
    graph = build_rag_graph()
    compiled = graph.compile()
    logger.info("LangGraph RAG graph compiled successfully")
    return compiled


# ── Module-level compiled graph (singleton) ──────────────────────────────────
_compiled_graph = None


def get_compiled_graph():
    """Return the compiled graph, building it on first call (lazy singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_graph()
    return _compiled_graph
