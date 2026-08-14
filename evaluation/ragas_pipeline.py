#!/usr/bin/env python3
"""
evaluation/ragas_pipeline.py
────────────────────────────
RAGAS evaluation pipeline for the Agentic RAG system.

Loads Q&A pairs from qa_validation.json, runs each query through the agent,
and computes RAGAS metrics:
  - context_relevancy:    Are retrieved docs relevant to the question?
  - answer_faithfulness:  Is the answer faithful to the retrieved context?
  - answer_relevancy:     Does the answer address the question?
  - context_recall:       Are all ground truth answers supported by context?

Usage:
    python evaluation/ragas_pipeline.py
    python evaluation/ragas_pipeline.py --output results/eval_2026_07.json
    python evaluation/ragas_pipeline.py --limit 3 --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logger import configure_logging, get_logger

configure_logging()
logger = get_logger("ragas_pipeline")


def load_qa_dataset(path: Path) -> list[dict]:
    """Load Q&A validation dataset from JSON file."""
    with open(path) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Q&A dataset must be a JSON array of objects")

    logger.info("Loaded QA dataset", extra={"count": len(data), "path": str(path)})
    return data


def run_agent_on_query(
    question: str,
    user_id: str = "eval_user",
    session_id: str = "eval_session",
) -> dict[str, Any]:
    """
    Run the agent pipeline on a single question and return the result.

    Returns:
        Dict with keys: answer, context_docs, latency_ms
    """
    from src.agents.graph import get_compiled_graph
    from src.agents.state import create_initial_state

    start = time.perf_counter()

    initial_state = create_initial_state(
        query=question,
        user_id=user_id,
        session_id=session_id,
        max_iterations=3,
    )

    graph = get_compiled_graph()
    final_state = graph.invoke(initial_state)

    elapsed_ms = (time.perf_counter() - start) * 1000

    answer = final_state.get("answer", "")
    context_docs = final_state.get("all_docs", [])

    return {
        "answer": answer,
        "context_docs": context_docs,
        "context_texts": [doc.page_content for doc in context_docs],
        "latency_ms": round(elapsed_ms, 1),
        "iterations": final_state.get("iterations", 0),
    }


def build_ragas_dataset(
    qa_pairs: list[dict],
    agent_results: list[dict],
) -> Any:
    """
    Build a RAGAS-compatible EvaluationDataset (ragas 0.2.x API).
    """
    try:
        # ragas 0.2.x API
        from ragas import EvaluationDataset, SingleTurnSample

        samples = []
        for qa, result in zip(qa_pairs, agent_results):
            retrieved_contexts = result["context_texts"]
            if not retrieved_contexts:
                retrieved_contexts = qa.get("contexts", ["No context retrieved."])

            samples.append(
                SingleTurnSample(
                    user_input=qa["question"],
                    response=result["answer"],
                    retrieved_contexts=retrieved_contexts,
                    reference=qa["ground_truth"],
                )
            )
        return EvaluationDataset(samples=samples)

    except ImportError:
        # Fallback: ragas 0.1.x API using HuggingFace Dataset
        from datasets import Dataset

        data: dict[str, list] = {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truths": [],
        }
        for qa, result in zip(qa_pairs, agent_results):
            data["question"].append(qa["question"])
            data["answer"].append(result["answer"])
            retrieved_contexts = result["context_texts"] or qa.get("contexts", ["No context retrieved."])
            data["contexts"].append(retrieved_contexts)
            data["ground_truths"].append([qa["ground_truth"]])

        return Dataset.from_dict(data)


def run_ragas_evaluation(dataset: Any, metrics: list | None = None) -> dict[str, float]:
    """
    Run RAGAS evaluation metrics on the dataset.
    Supports both ragas 0.2.x and 0.1.x APIs.

    Returns:
        Dict mapping metric name to score.
    """
    from ragas import evaluate

    try:
        # ragas 0.2.x metric names
        from ragas.metrics import (
            ContextRelevance,
            Faithfulness,
            ResponseRelevancy,
            ContextRecall,
        )
        selected_metrics = metrics or [
            ContextRelevance(),
            Faithfulness(),
            ResponseRelevancy(),
            ContextRecall(),
        ]
    except ImportError:
        # ragas 0.1.x metric names
        from ragas.metrics import (
            context_relevancy,
            faithfulness,
            answer_relevancy,
            context_recall,
        )
        selected_metrics = metrics or [
            context_relevancy,
            faithfulness,
            answer_relevancy,
            context_recall,
        ]

    metric_names = [
        m.name if hasattr(m, "name") else type(m).__name__
        for m in selected_metrics
    ]
    logger.info("Running RAGAS evaluation", extra={"metrics": metric_names})

    result = evaluate(
        dataset=dataset,
        metrics=selected_metrics,
    )

    return result


def save_results(
    results: dict,
    agent_results: list[dict],
    qa_pairs: list[dict],
    output_path: Path,
) -> None:
    """Save evaluation results to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import arrow

    report = {
        "timestamp": arrow.utcnow().isoformat(),
        "summary": {
            "num_questions": len(qa_pairs),
            "avg_latency_ms": round(
                sum(r["latency_ms"] for r in agent_results) / len(agent_results), 1
            ),
            "avg_iterations": round(
                sum(r["iterations"] for r in agent_results) / len(agent_results), 2
            ),
        },
        "ragas_scores": results,
        "per_question": [
            {
                "question": qa["question"],
                "answer": result["answer"],
                "latency_ms": result["latency_ms"],
                "iterations": result["iterations"],
                "contexts_retrieved": len(result["context_texts"]),
            }
            for qa, result in zip(qa_pairs, agent_results)
        ],
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Results saved", extra={"path": str(output_path)})


def print_report(ragas_scores: dict, agent_results: list[dict]) -> None:
    """Print a formatted evaluation report to stdout."""
    print("\n" + "═" * 60)
    print("  RAGAS Evaluation Report")
    print("═" * 60)

    print("\n📊 RAGAS Metric Scores:")
    for metric, score in ragas_scores.items():
        emoji = "✅" if score >= 0.7 else ("⚠️" if score >= 0.5 else "❌")
        print(f"   {emoji} {metric:<30} {score:.4f}")

    print("\n⚡ Agent Performance:")
    latencies = [r["latency_ms"] for r in agent_results]
    iterations = [r["iterations"] for r in agent_results]
    print(f"   Avg latency:    {sum(latencies)/len(latencies):.1f}ms")
    print(f"   Max latency:    {max(latencies):.1f}ms")
    print(f"   Avg iterations: {sum(iterations)/len(iterations):.2f}")

    print("\n" + "═" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run RAGAS evaluation on the Agentic RAG pipeline",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).parent / "datasets" / "qa_validation.json",
        help="Path to Q&A validation JSON file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "results" / f"eval_{int(time.time())}.json",
        help="Path to save evaluation results",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of questions to evaluate (for quick testing)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed per-question results",
    )
    parser.add_argument(
        "--skip-agent",
        action="store_true",
        help="Skip agent execution; use ground truth contexts instead (for offline eval)",
    )

    args = parser.parse_args()

    print("═══════════════════════════════════════════════")
    print("  Agentic RAG — RAGAS Evaluation Pipeline")
    print("═══════════════════════════════════════════════\n")

    # Load dataset
    qa_pairs = load_qa_dataset(args.dataset)
    if args.limit:
        qa_pairs = qa_pairs[: args.limit]
        print(f"⚠️  Limited to {args.limit} questions\n")

    print(f"📋 Evaluating {len(qa_pairs)} questions...\n")

    # Run agent on each question
    agent_results = []
    for i, qa in enumerate(qa_pairs):
        print(f"  [{i+1}/{len(qa_pairs)}] {qa['question'][:70]}...")

        if args.skip_agent:
            # Use ground truth contexts for offline/fast evaluation
            agent_results.append({
                "answer": qa.get("ground_truth", ""),
                "context_docs": [],
                "context_texts": qa.get("contexts", []),
                "latency_ms": 0.0,
                "iterations": 0,
            })
        else:
            try:
                result = run_agent_on_query(
                    question=qa["question"],
                    session_id=f"eval_session_{i}",
                )
                agent_results.append(result)
                if args.verbose:
                    print(f"     Answer: {result['answer'][:120]}...")
                    print(f"     Latency: {result['latency_ms']}ms | Iterations: {result['iterations']}")
            except Exception as e:
                logger.error("Agent failed on question", extra={"question": qa["question"][:60], "error": str(e)})
                agent_results.append({
                    "answer": "Error: agent failed to produce an answer.",
                    "context_docs": [],
                    "context_texts": qa.get("contexts", []),
                    "latency_ms": 0.0,
                    "iterations": 0,
                })

    print("\n🔬 Running RAGAS metrics...")

    try:
        # Build RAGAS dataset
        ragas_dataset = build_ragas_dataset(qa_pairs, agent_results)

        # Run evaluation
        ragas_result = run_ragas_evaluation(ragas_dataset)

        # Convert to plain dict
        ragas_scores = dict(ragas_result)

        # Print report
        print_report(ragas_scores, agent_results)

        # Save results
        save_results(ragas_scores, agent_results, qa_pairs, args.output)
        print(f"\n💾 Results saved to: {args.output}")

    except ImportError as e:
        print(f"\n❌ RAGAS import failed: {e}")
        print("   Install with: pip install ragas datasets")
        print("\n📊 Agent Performance Only (RAGAS unavailable):")
        latencies = [r["latency_ms"] for r in agent_results]
        if latencies:
            print(f"   Avg latency: {sum(latencies)/len(latencies):.1f}ms")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        logger.error("RAGAS evaluation failed", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
