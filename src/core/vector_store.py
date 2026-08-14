"""
src/core/vector_store.py
────────────────────────
Qdrant vector store wrapper with collection management,
upsert, similarity search, and deletion utilities.
"""
from __future__ import annotations

import uuid
from typing import Any

from langchain_core.documents import Document
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import Settings, get_settings
from src.core.exceptions import VectorStoreError
from src.utils.logger import get_logger
from src.utils.metrics import VECTOR_STORE_OPS

logger = get_logger(__name__)


class QdrantVectorStore:
    """
    Wrapper around QdrantClient providing:
    - Collection management (create / ensure / delete)
    - Document upsert with automatic embedding
    - Similarity search with optional metadata filters
    - Async support via AsyncQdrantClient
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: QdrantClient | None = None
        self._async_client: AsyncQdrantClient | None = None
        self._embeddings = None  # lazy-loaded

    # ── Client Initialization ─────────────────────────────────────────────────

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            try:
                self._client = QdrantClient(
                    host=self.settings.qdrant_host,
                    port=self.settings.qdrant_port,
                    timeout=30,
                )
                logger.info("Qdrant sync client initialized", extra={"host": self.settings.qdrant_host})
            except Exception as e:
                raise VectorStoreError(f"Failed to connect to Qdrant: {e}") from e
        return self._client

    def _get_async_client(self) -> AsyncQdrantClient:
        if self._async_client is None:
            self._async_client = AsyncQdrantClient(
                host=self.settings.qdrant_host,
                port=self.settings.qdrant_port,
                timeout=30,
            )
        return self._async_client

    def _get_embeddings(self):
        """Lazy-load embeddings model based on provider."""
        if self._embeddings is None:
            if self.settings.llm_provider == "openai":
                from langchain_openai import OpenAIEmbeddings
                self._embeddings = OpenAIEmbeddings(
                    model=self.settings.openai_embedding_model,
                    api_key=self.settings.openai_api_key,
                )
            else:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
                self._embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/embedding-001",
                    google_api_key=self.settings.gemini_api_key,
                )
        return self._embeddings

    # ── Collection Management ─────────────────────────────────────────────────

    def ensure_collection(
        self,
        collection_name: str,
        vector_size: int | None = None,
    ) -> bool:
        """Create collection if it doesn't exist. Returns True if newly created."""
        client = self._get_client()
        size = vector_size or self.settings.qdrant_vector_size

        existing = [c.name for c in client.get_collections().collections]
        if collection_name in existing:
            logger.debug("Collection already exists", extra={"collection": collection_name})
            return False

        client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=size,
                distance=qmodels.Distance.COSINE,
            ),
            optimizers_config=qmodels.OptimizersConfigDiff(
                indexing_threshold=20_000,
            ),
            hnsw_config=qmodels.HnswConfigDiff(
                m=16,
                ef_construct=100,
            ),
        )
        logger.info("Created Qdrant collection", extra={"collection": collection_name, "size": size})
        return True

    def delete_collection(self, collection_name: str) -> None:
        """Delete a Qdrant collection entirely."""
        client = self._get_client()
        try:
            client.delete_collection(collection_name)
            logger.info("Deleted Qdrant collection", extra={"collection": collection_name})
        except UnexpectedResponse as e:
            raise VectorStoreError(f"Failed to delete collection '{collection_name}': {e}") from e

    def collection_info(self, collection_name: str) -> dict[str, Any]:
        """Return collection metadata (count, status, etc.)."""
        client = self._get_client()
        info = client.get_collection(collection_name)
        return {
            "name": collection_name,
            "status": info.status,
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "points_count": info.points_count,
        }

    # ── Document Operations ───────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def upsert_documents(
        self,
        documents: list[Document],
        collection_name: str | None = None,
        batch_size: int = 100,
    ) -> int:
        """Embed and upsert documents into Qdrant. Returns number of upserted points."""
        collection = collection_name or self.settings.qdrant_collection_name
        self.ensure_collection(collection)
        embeddings_model = self._get_embeddings()

        total_upserted = 0
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            texts = [doc.page_content for doc in batch]
            vectors = embeddings_model.embed_documents(texts)

            points = [
                qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "page_content": doc.page_content,
                        "metadata": doc.metadata,
                    },
                )
                for doc, vector in zip(batch, vectors)
            ]

            self._get_client().upsert(collection_name=collection, points=points, wait=True)
            total_upserted += len(points)
            VECTOR_STORE_OPS.labels(operation="upsert", collection=collection).inc(len(points))
            logger.debug(
                "Upserted batch",
                extra={"collection": collection, "batch_size": len(points), "total": total_upserted},
            )

        return total_upserted

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    def similarity_search(
        self,
        query: str,
        k: int = 5,
        collection_name: str | None = None,
        score_threshold: float = 0.5,
        filter_conditions: dict | None = None,
    ) -> list[Document]:
        """Perform cosine similarity search against a collection."""
        collection = collection_name or self.settings.qdrant_collection_name
        embeddings_model = self._get_embeddings()

        query_vector = embeddings_model.embed_query(query)

        qdrant_filter = None
        if filter_conditions:
            qdrant_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key=f"metadata.{k}",
                        match=qmodels.MatchValue(value=v),
                    )
                    for k, v in filter_conditions.items()
                ]
            )

        results = self._get_client().search(
            collection_name=collection,
            query_vector=query_vector,
            limit=k,
            score_threshold=score_threshold,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        VECTOR_STORE_OPS.labels(operation="search", collection=collection).inc()
        documents = [
            Document(
                page_content=hit.payload.get("page_content", ""),
                metadata={**hit.payload.get("metadata", {}), "_score": hit.score},
            )
            for hit in results
        ]
        logger.debug(
            "Similarity search complete",
            extra={"collection": collection, "query": query[:60], "results": len(documents)},
        )
        return documents

    def delete_by_metadata(
        self,
        filter_conditions: dict[str, Any],
        collection_name: str | None = None,
    ) -> int:
        """Delete points matching metadata filter. Returns count of deleted points."""
        collection = collection_name or self.settings.qdrant_collection_name
        client = self._get_client()

        must_conditions = [
            qmodels.FieldCondition(
                key=f"metadata.{k}",
                match=qmodels.MatchValue(value=v),
            )
            for k, v in filter_conditions.items()
        ]

        result = client.delete(
            collection_name=collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(must=must_conditions)
            ),
        )
        VECTOR_STORE_OPS.labels(operation="delete", collection=collection).inc()
        return result.status.value if hasattr(result.status, "value") else 0

    def close(self) -> None:
        """Close client connections."""
        if self._client:
            self._client.close()
        if self._async_client:
            import asyncio
            try:
                asyncio.get_event_loop().run_until_complete(self._async_client.close())
            except Exception:
                pass
