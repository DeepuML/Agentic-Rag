"""
src/data_ingestion/chunking.py
───────────────────────────────
Text chunking strategies for splitting documents into smaller pieces
before embedding and storing in Qdrant.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.utils.helpers import compute_content_hash
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ChunkingStrategy(str, Enum):
    RECURSIVE = "recursive"
    SENTENCE = "sentence"
    FIXED = "fixed"


class DocumentChunker:
    """
    Splits documents into smaller chunks for embedding.

    Supports three strategies:
      - recursive: Recursively split on paragraph/sentence/word boundaries (best for most text)
      - sentence: Split on sentence boundaries
      - fixed: Fixed-size character windows with overlap
    """

    def __init__(
        self,
        strategy: ChunkingStrategy | str = ChunkingStrategy.RECURSIVE,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> None:
        self.strategy = ChunkingStrategy(strategy)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = self._build_splitter()

    def _build_splitter(self) -> RecursiveCharacterTextSplitter:
        """Build the appropriate text splitter."""
        if self.strategy == ChunkingStrategy.RECURSIVE:
            return RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
                length_function=len,
            )
        elif self.strategy == ChunkingStrategy.SENTENCE:
            return RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=[". ", "! ", "? ", "\n", " "],
                length_function=len,
            )
        else:  # FIXED
            return RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=[" ", ""],
                length_function=len,
            )

    def chunk_document(self, document: Document) -> list[Document]:
        """
        Split a single document into chunks.
        Preserves all metadata and adds chunk-specific metadata.
        Deduplicates chunks by content hash.
        """
        if not document.page_content.strip():
            return []

        chunks = self._splitter.split_documents([document])

        seen_hashes: set[str] = set()
        unique_chunks: list[Document] = []

        for i, chunk in enumerate(chunks):
            content_hash = compute_content_hash(chunk.page_content)
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)

            # Add chunk metadata
            chunk.metadata.update({
                "chunk_index": i,
                "chunk_total": len(chunks),
                "content_hash": content_hash,
                "chunk_size": len(chunk.page_content),
            })
            unique_chunks.append(chunk)

        logger.debug(
            "Document chunked",
            extra={
                "source_id": document.metadata.get("source_id", "unknown"),
                "chunks": len(unique_chunks),
                "strategy": self.strategy.value,
            },
        )
        return unique_chunks

    def chunk_documents(self, documents: list[Document]) -> list[Document]:
        """Chunk a list of documents, returning all chunks."""
        all_chunks: list[Document] = []
        for doc in documents:
            chunks = self.chunk_document(doc)
            all_chunks.extend(chunks)

        logger.info(
            "Batch chunking complete",
            extra={
                "input_docs": len(documents),
                "output_chunks": len(all_chunks),
            },
        )
        return all_chunks


def get_default_chunker() -> DocumentChunker:
    """Return the default chunker with settings from connectors.yaml."""
    try:
        from pathlib import Path
        import yaml
        from src.core.config import get_settings

        config_path = get_settings().configs_dir / "connectors.yaml"
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f).get("chunking", {})
            return DocumentChunker(
                strategy=config.get("strategy", "recursive"),
                chunk_size=config.get("chunk_size", 512),
                chunk_overlap=config.get("chunk_overlap", 64),
            )
    except Exception:
        pass
    return DocumentChunker()
