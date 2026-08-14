"""
src/data_ingestion/pipeline.py
───────────────────────────────
Main ingestion pipeline that:
  1. Runs all connectors to fetch raw documents
  2. Chunks documents using DocumentChunker
  3. Upserts chunks into Qdrant vector store
  4. Runs on an infinite loop with configurable poll interval
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from langchain_core.documents import Document

from src.core.config import get_settings
from src.core.vector_store import QdrantVectorStore
from src.data_ingestion.base_connector import BaseConnector
from src.data_ingestion.chunking import get_default_chunker
from src.data_ingestion.connectors.gmail_connector import GmailConnector
from src.data_ingestion.connectors.notion_connector import NotionConnector
from src.data_ingestion.connectors.jira_connector import JiraConnector
from src.utils.logger import get_logger
from src.utils.metrics import DOCS_INGESTED, INGESTION_RUNS

logger = get_logger(__name__)


class IngestionPipeline:
    """
    Orchestrates the full data ingestion pipeline:
        Connectors → Chunker → Vector Store

    Run modes:
        - run_once(): Run all connectors once and return.
        - run_loop(): Infinite polling loop (for background thread).
    """

    def __init__(
        self,
        connectors: list[BaseConnector] | None = None,
        vector_store: QdrantVectorStore | None = None,
    ) -> None:
        self.settings = get_settings()
        self.connectors = connectors or self._default_connectors()
        self.vector_store = vector_store or QdrantVectorStore()
        self.chunker = get_default_chunker()
        self._running = False

    def _default_connectors(self) -> list[BaseConnector]:
        """Return the default set of connectors."""
        return [
            GmailConnector(),
            NotionConnector(),
            JiraConnector(),
        ]

    def run_once(self) -> dict[str, Any]:
        """
        Run one full ingestion cycle across all connectors.

        Returns:
            Summary dict with per-connector counts.
        """
        summary: dict[str, Any] = {
            "connectors_run": [],
            "connectors_failed": [],
            "total_docs_fetched": 0,
            "total_chunks_ingested": 0,
        }

        # Ensure collection exists
        self.vector_store.ensure_collection(self.settings.qdrant_collection_name)

        for connector in self.connectors:
            try:
                logger.info("Starting ingestion", extra={"connector": connector.name})
                raw_docs = connector.fetch_documents()

                if not raw_docs:
                    logger.info("No documents fetched", extra={"connector": connector.name})
                    summary["connectors_run"].append(connector.name)
                    continue

                # Convert to LangChain Documents
                lc_docs: list[Document] = [doc.to_document() for doc in raw_docs]

                # Chunk
                chunks = self.chunker.chunk_documents(lc_docs)

                if not chunks:
                    logger.warning("Chunking produced no chunks", extra={"connector": connector.name})
                    continue

                # Upsert to Qdrant
                upserted = self.vector_store.upsert_documents(
                    chunks,
                    collection_name=self.settings.qdrant_collection_name,
                )

                DOCS_INGESTED.labels(connector=connector.name).inc(upserted)
                INGESTION_RUNS.labels(connector=connector.name, status="success").inc()

                summary["connectors_run"].append(connector.name)
                summary["total_docs_fetched"] += len(raw_docs)
                summary["total_chunks_ingested"] += upserted

                logger.info(
                    "Ingestion complete for connector",
                    extra={
                        "connector": connector.name,
                        "raw_docs": len(raw_docs),
                        "chunks": upserted,
                    },
                )

            except Exception as e:
                INGESTION_RUNS.labels(connector=connector.name, status="failure").inc()
                summary["connectors_failed"].append(connector.name)
                logger.error(
                    "Connector ingestion failed",
                    extra={"connector": connector.name, "error": str(e)},
                )

        return summary

    def run_loop(self, poll_interval: int | None = None) -> None:
        """
        Run an infinite ingestion loop with configurable poll interval.
        Designed to run in a background thread.

        Args:
            poll_interval: Seconds between cycles. Defaults to settings value.
        """
        interval = poll_interval or self.settings.ingestion_poll_interval_seconds
        self._running = True

        logger.info(
            "Ingestion pipeline started",
            extra={"interval_seconds": interval, "connectors": [c.name for c in self.connectors]},
        )

        while self._running:
            try:
                start = time.monotonic()
                summary = self.run_once()
                elapsed = time.monotonic() - start

                logger.info(
                    "Ingestion cycle complete",
                    extra={
                        **summary,
                        "elapsed_seconds": round(elapsed, 2),
                        "next_run_in": interval,
                    },
                )

            except Exception as e:
                logger.error("Ingestion loop error", extra={"error": str(e)})

            # Wait for next cycle
            time.sleep(interval)

    def stop(self) -> None:
        """Signal the ingestion loop to stop after the current cycle."""
        self._running = False
        logger.info("Ingestion pipeline stop requested")

    def health_check(self) -> dict[str, bool]:
        """Check health of all connectors."""
        return {
            connector.name: connector.health_check()
            for connector in self.connectors
        }
