"""
src/agents/nodes.py
───────────────────
The five node functions that make up the Agentic RAG pipeline:
    1. planner   – Decides search strategy
    2. retriever – Fetches documents from Qdrant
    3. evaluator – Judges if retrieved docs are sufficient
    4. reflector – Reformulates the query if docs are insufficient
    5. generator – Produces the final grounded answer
"""
from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from src.agents.state import AgentState
from src.agents.tools import get_vector_store
from src.core.config import get_settings
from src.core.exceptions import MaxIterationsExceededError, RetrievalError
from src.utils.logger import get_logger
from src.utils.metrics import AGENT_ITERATIONS

logger = get_logger(__name__)


# ── LLM Factory ───────────────────────────────────────────────────────────────

def _get_llm(temperature: float = 0.0):
    """Return the configured LLM client."""
    settings = get_settings()
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.openai_model,
            temperature=temperature,
            api_key=settings.openai_api_key,
        )
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            temperature=temperature,
            google_api_key=settings.gemini_api_key,
        )


# ── Node 1: Planner ───────────────────────────────────────────────────────────

PLANNER_SYSTEM = """You are a search strategy planner for a RAG system with access to 
documents from Gmail, Notion, and Jira.

Given a user query (and optionally decomposed sub-questions), decide:
1. The primary search strategy (semantic | keyword | hybrid)
2. Which data sources are most relevant (gmail, notion, jira, or all)
3. Key terms or concepts to focus on during retrieval

Respond in JSON with keys: strategy, sources, key_terms, reasoning"""

PLANNER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", PLANNER_SYSTEM),
    ("human", "User Query: {query}\n\nSub-questions: {sub_questions}"),
])


def planner(state: AgentState) -> dict[str, Any]:
    """
    Node 1 — Planner
    Decides the retrieval strategy based on the user's query.
    Sets the 'plan' field in state.
    """
    logger.info("Planner node executing", extra={"query": state["query"][:60]})

    llm = _get_llm(temperature=0.0)
    chain = PLANNER_PROMPT | llm

    sub_q_text = "\n".join(f"- {q}" for q in state.get("sub_questions", [])) or "None"

    try:
        response = chain.invoke({
            "query": state["query"],
            "sub_questions": sub_q_text,
        })
        plan = response.content
    except Exception as e:
        logger.warning("Planner LLM call failed, using default plan", extra={"error": str(e)})
        plan = '{"strategy": "semantic", "sources": ["all"], "key_terms": [], "reasoning": "Fallback"}'

    logger.debug("Plan created", extra={"plan": plan[:200]})
    return {"plan": plan}


# ── Node 2: Retriever ─────────────────────────────────────────────────────────

def retriever(state: AgentState) -> dict[str, Any]:
    """
    Node 2 — Retriever
    Fetches relevant documents from Qdrant using the current query.
    Accumulates results in 'all_docs'.
    """
    query = state["query"]
    iterations = state.get("iterations", 0)

    logger.info(
        "Retriever node executing",
        extra={"query": query[:60], "iteration": iterations},
    )

    vs = get_vector_store()
    settings = get_settings()

    try:
        docs = vs.similarity_search(
            query=query,
            k=5,
            score_threshold=0.45,
            collection_name=settings.qdrant_collection_name,
        )
    except Exception as e:
        logger.error("Retrieval failed", extra={"error": str(e), "query": query[:60]})
        raise RetrievalError(query=query, reason=str(e)) from e

    # Also retrieve sub-questions if present
    all_retrieved = list(docs)
    for sub_q in state.get("sub_questions", [])[:2]:  # limit sub-question retrievals
        try:
            sub_docs = vs.similarity_search(query=sub_q, k=3, score_threshold=0.50)
            all_retrieved.extend(sub_docs)
        except Exception:
            pass

    # Deduplicate by content hash
    seen_hashes: set[str] = set()
    unique_docs: list[Document] = []
    for doc in all_retrieved:
        content_hash = hash(doc.page_content[:200])
        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            unique_docs.append(doc)

    # Merge with previously accumulated docs
    existing_all_docs = state.get("all_docs", [])
    merged_docs = existing_all_docs + unique_docs

    new_iterations = iterations + 1
    AGENT_ITERATIONS.observe(new_iterations)

    logger.info(
        "Retriever complete",
        extra={
            "new_docs": len(unique_docs),
            "total_docs": len(merged_docs),
            "iteration": new_iterations,
        },
    )

    return {
        "context_docs": unique_docs,
        "all_docs": merged_docs,
        "iterations": new_iterations,
    }


# ── Node 3: Evaluator ─────────────────────────────────────────────────────────

EVALUATOR_SYSTEM = """You are a relevance evaluator for a RAG system.

Given a user query and a list of retrieved document snippets, determine if the 
documents collectively contain sufficient information to answer the query.

Respond with ONLY one of:
- "SUFFICIENT" — if the documents can support a complete answer
- "INSUFFICIENT" — if the documents are missing key information

Do not add any other text."""

EVALUATOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", EVALUATOR_SYSTEM),
    ("human", (
        "Query: {query}\n\n"
        "Retrieved documents:\n{docs_summary}\n\n"
        "Are these documents SUFFICIENT or INSUFFICIENT?"
    )),
])


def evaluator(state: AgentState) -> dict[str, Any]:
    """
    Node 3 — Evaluator
    Assesses whether the retrieved documents are sufficient to answer the query.
    Sets 'is_sufficient' in state.
    """
    query = state["query"]
    context_docs = state.get("context_docs", [])
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 3)

    logger.info(
        "Evaluator node executing",
        extra={"num_docs": len(context_docs), "iteration": iterations},
    )

    # Force sufficient if at max iterations to prevent infinite loop
    if iterations >= max_iterations:
        logger.warning(
            "Max iterations reached, forcing SUFFICIENT",
            extra={"max_iterations": max_iterations},
        )
        return {"is_sufficient": True}

    if not context_docs:
        logger.info("No documents retrieved, marking INSUFFICIENT")
        return {"is_sufficient": False}

    # Build a summary of docs for evaluation
    docs_summary = "\n---\n".join(
        f"[Doc {i+1}] {doc.page_content[:300]}"
        for i, doc in enumerate(context_docs[:5])
    )

    llm = _get_llm(temperature=0.0)
    chain = EVALUATOR_PROMPT | llm

    try:
        response = chain.invoke({"query": query, "docs_summary": docs_summary})
        verdict = response.content.strip().upper()
        is_sufficient = "SUFFICIENT" in verdict and "INSUFFICIENT" not in verdict
    except Exception as e:
        logger.warning("Evaluator LLM call failed, defaulting to SUFFICIENT", extra={"error": str(e)})
        is_sufficient = True

    logger.info("Evaluator verdict", extra={"is_sufficient": is_sufficient})
    return {"is_sufficient": is_sufficient}


# ── Node 4: Reflector ─────────────────────────────────────────────────────────

REFLECTOR_SYSTEM = """You are a query reformulation specialist.

The initial retrieval was INSUFFICIENT. Your job is to reformulate the query to 
retrieve better documents. Consider:
- Use different terminology or synonyms
- Broaden or narrow the scope
- Focus on specific aspects of the original question
- Break into more specific terms

Return ONLY the reformulated query — no explanation."""

REFLECTOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", REFLECTOR_SYSTEM),
    ("human", (
        "Original query: {original_query}\n"
        "Current (failing) query: {current_query}\n"
        "Attempt number: {iteration}\n\n"
        "Documents retrieved so far (for context):\n{docs_preview}\n\n"
        "Write an improved query:"
    )),
])


def reflector(state: AgentState) -> dict[str, Any]:
    """
    Node 4 — Reflector
    Reformulates the query when the evaluator finds retrieved docs insufficient.
    """
    logger.info(
        "Reflector node executing",
        extra={
            "original_query": state["original_query"][:60],
            "current_query": state["query"][:60],
            "iteration": state.get("iterations", 0),
        },
    )

    docs_preview = "\n".join(
        f"- {doc.page_content[:150]}"
        for doc in state.get("all_docs", [])[:3]
    ) or "No documents retrieved yet."

    llm = _get_llm(temperature=0.3)
    chain = REFLECTOR_PROMPT | llm

    try:
        response = chain.invoke({
            "original_query": state["original_query"],
            "current_query": state["query"],
            "iteration": state.get("iterations", 0),
            "docs_preview": docs_preview,
        })
        new_query = response.content.strip()
    except Exception as e:
        logger.warning("Reflector LLM call failed, keeping original query", extra={"error": str(e)})
        new_query = state["original_query"]

    logger.info("Query reformulated", extra={"new_query": new_query[:100]})
    return {"query": new_query}


# ── Node 5: Generator ─────────────────────────────────────────────────────────

GENERATOR_SYSTEM = """You are a helpful AI assistant that answers questions strictly 
based on the provided context documents.

Rules:
1. ONLY use information present in the context documents.
2. If the context does not contain enough information, say so clearly.
3. Cite your sources by referencing the document metadata when possible.
4. Be concise, factual, and professional.
5. Do not hallucinate or add information from your training data.
6. Structure your answer with clear paragraphs if the answer is long."""

GENERATOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", GENERATOR_SYSTEM),
    ("human", (
        "Context Documents:\n{context}\n\n"
        "User Question: {question}\n\n"
        "Answer based ONLY on the context above:"
    )),
])


def generator(state: AgentState) -> dict[str, Any]:
    """
    Node 5 — Generator
    Produces the final answer using the accumulated context documents.
    """
    query = state["original_query"]  # Answer the original query, not a reformulation
    all_docs = state.get("all_docs", [])
    context_docs = state.get("context_docs", [])

    # Use all accumulated docs, prefer most relevant (all_docs includes context_docs)
    docs_to_use = all_docs if all_docs else context_docs

    logger.info(
        "Generator node executing",
        extra={"query": query[:60], "num_docs": len(docs_to_use)},
    )

    if not docs_to_use:
        no_context_answer = (
            "I was unable to find relevant information in the available documents "
            "to answer your question. Please check that the data has been ingested "
            "or try rephrasing your query."
        )
        return {
            "answer": no_context_answer,
            "messages": [AIMessage(content=no_context_answer)],
        }

    # Build context string with source attribution
    context_parts = []
    for i, doc in enumerate(docs_to_use[:8]):  # limit to top 8 docs
        source = doc.metadata.get("source", f"Document {i+1}")
        source_id = doc.metadata.get("source_id", "")
        header = f"[Source {i+1}: {source}" + (f" / {source_id}]" if source_id else "]")
        context_parts.append(f"{header}\n{doc.page_content}")
    context = "\n\n".join(context_parts)

    llm = _get_llm(temperature=0.1)
    chain = GENERATOR_PROMPT | llm

    try:
        response = chain.invoke({"context": context, "question": query})
        answer = response.content.strip()
    except Exception as e:
        logger.error("Generator LLM call failed", extra={"error": str(e)})
        answer = (
            "I encountered an error generating a response. Please try again."
        )

    logger.info("Generator complete", extra={"answer_len": len(answer)})

    return {
        "answer": answer,
        "messages": [
            HumanMessage(content=query),
            AIMessage(content=answer),
        ],
    }
