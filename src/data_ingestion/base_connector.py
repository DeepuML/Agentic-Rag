"""
src/data_ingestion/base_connector.py
──────────────────────────────────────
Abstract base class for all data source connectors.
Every connector (Gmail, Notion, Jira) must implement this interface.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from langchain_core.documents import Document


@dataclass
class RawDocument:
    """
    Raw document fetched from a data source before chunking/embedding.
    """
    source: str                     # "gmail" | "notion" | "jira"
    source_id: str                  # Unique ID in the source system
    title: str
    content: str
    url: str = ""
    author: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def to_document(self) -> Document:
        """Convert to a LangChain Document for downstream processing."""
        return Document(
            page_content=self.content,
            metadata={
                "source": self.source,
                "source_id": self.source_id,
                "title": self.title,
                "url": self.url,
                "author": self.author,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "tags": ",".join(self.tags),
                **self.extra_metadata,
            },
        )


class BaseConnector(abc.ABC):
    """
    Abstract base class for all data source connectors.

    Subclasses must implement:
      - `name` property
      - `fetch_documents()` method
      - `health_check()` method
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Connector name (e.g., 'gmail', 'notion', 'jira')."""
        ...

    @abc.abstractmethod
    def fetch_documents(self) -> list[RawDocument]:
        """
        Fetch documents from the data source.

        Returns:
            List of RawDocument objects ready for ingestion.

        Raises:
            ConnectorError: If fetching fails.
        """
        ...

    @abc.abstractmethod
    def health_check(self) -> bool:
        """
        Check if the connector can reach the data source.

        Returns:
            True if healthy, False otherwise.
        """
        ...

    def get_config(self) -> dict[str, Any]:
        """Return connector-specific configuration. Override as needed."""
        return {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
