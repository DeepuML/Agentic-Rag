"""
src/data_ingestion/connectors/notion_connector.py
──────────────────────────────────────────────────
Notion connector that fetches pages and database rows.
Mock mode returns realistic Notion content for development.
"""
from __future__ import annotations

from typing import Any

from src.core.config import get_settings
from src.core.exceptions import ConnectorError
from src.data_ingestion.base_connector import BaseConnector, RawDocument
from src.utils.logger import get_logger

logger = get_logger(__name__)


_MOCK_NOTION_PAGES: list[dict[str, Any]] = [
    {
        "id": "notion_page_001",
        "title": "Engineering Onboarding Guide",
        "content": (
            "# Engineering Onboarding Guide\n\n"
            "## Welcome to the Engineering Team\n\n"
            "This guide will help you get set up in your first two weeks.\n\n"
            "### Week 1: Setup & Orientation\n\n"
            "**Day 1-2: Environment Setup**\n"
            "- Install required tools: Python 3.12, Docker, VS Code\n"
            "- Clone the main repository: `git clone https://github.com/company/platform`\n"
            "- Set up local development environment following `docs/setup.md`\n"
            "- Request access to AWS, Datadog, and PagerDuty\n\n"
            "**Day 3-4: Codebase Tour**\n"
            "- Review architecture diagram in Confluence\n"
            "- Meet with team leads for domain introductions\n"
            "- Shadow a senior engineer for code reviews\n\n"
            "**Day 5: First PR**\n"
            "- Pick up a 'good-first-issue' from PROJ board\n"
            "- Submit your first pull request\n\n"
            "### Week 2: Deep Dive\n\n"
            "- Pair programming sessions scheduled with Alex\n"
            "- Complete security training (mandatory)\n"
            "- Review on-call rotation and runbooks\n"
            "- Complete first independent ticket\n"
        ),
        "url": "https://notion.so/engineering-onboarding",
        "last_edited_time": "2026-07-20T10:00:00Z",
        "created_time": "2026-01-15T08:00:00Z",
        "tags": ["engineering", "onboarding", "documentation"],
    },
    {
        "id": "notion_page_002",
        "title": "Q3 2026 Product Roadmap",
        "content": (
            "# Q3 2026 Product Roadmap\n\n"
            "## Goals\n"
            "Drive 30% improvement in search relevancy and reduce P95 latency to <200ms.\n\n"
            "## Initiatives\n\n"
            "### 1. Semantic Search (Priority: P0)\n"
            "- Deploy vector search using Qdrant\n"
            "- Implement hybrid search (BM25 + vector)\n"
            "- A/B test against current keyword search\n"
            "- Target: 40% improvement in search quality scores\n"
            "- Owner: Priya | Deadline: Sep 30\n\n"
            "### 2. AI-Powered Recommendations (Priority: P1)\n"
            "- Collaborative filtering model for 'You might also like'\n"
            "- Real-time recommendation API\n"
            "- Dashboard for recommendation analytics\n"
            "- Owner: Jordan | Deadline: Oct 15\n\n"
            "### 3. Performance Optimization (Priority: P1)\n"
            "- Database query optimization audit\n"
            "- CDN configuration for static assets\n"
            "- API response caching with Redis\n"
            "- Owner: Morgan | Deadline: Sep 15\n\n"
            "## Key Metrics\n"
            "- Search P95 latency: 450ms → 200ms\n"
            "- Search relevancy score: 0.62 → 0.87\n"
            "- Recommendation CTR: 3.2% → 5.5%\n"
        ),
        "url": "https://notion.so/q3-roadmap",
        "last_edited_time": "2026-07-22T14:00:00Z",
        "created_time": "2026-07-01T09:00:00Z",
        "tags": ["roadmap", "product", "Q3", "planning"],
    },
    {
        "id": "notion_page_003",
        "title": "System Design: Notification Service",
        "content": (
            "# System Design: Notification Service\n\n"
            "## Overview\n"
            "Event-driven notification service supporting email, SMS, and push channels.\n\n"
            "## Architecture\n\n"
            "```\n"
            "Producer → Kafka → Consumer Groups → Channel Adapters → Delivery\n"
            "```\n\n"
            "### Components\n"
            "- **Event Producer**: REST API ingesting notification events\n"
            "- **Kafka Topics**: One topic per channel (email, sms, push)\n"
            "- **Consumer Groups**: Auto-scaling worker pools\n"
            "- **Channel Adapters**: SendGrid (email), Twilio (SMS), FCM (push)\n"
            "- **Dead Letter Queue**: Failed notifications for retry\n\n"
            "## Scaling Strategy\n"
            "- Horizontal scaling via Kubernetes HPA\n"
            "- Target: 100,000 notifications/hour\n"
            "- SLA: 99.9% delivery within 30 seconds\n\n"
            "## Status: Approved for Implementation\n"
        ),
        "url": "https://notion.so/notification-service-design",
        "last_edited_time": "2026-07-18T11:30:00Z",
        "created_time": "2026-07-10T09:00:00Z",
        "tags": ["system-design", "backend", "architecture"],
    },
]


class NotionConnector(BaseConnector):
    """
    Notion connector fetching pages and database rows.

    Production setup:
        1. Create a Notion integration at https://www.notion.so/my-integrations
        2. Share your workspace/database with the integration
        3. Set NOTION_API_TOKEN and NOTION_DATABASE_ID in .env
        4. Set USE_MOCK_CONNECTORS=false
    """

    @property
    def name(self) -> str:
        return "notion"

    def fetch_documents(self) -> list[RawDocument]:
        """Fetch pages from Notion."""
        settings = get_settings()

        if settings.use_mock_connectors:
            logger.info("Notion connector: using mock data")
            return self._fetch_mock()

        logger.info("Notion connector: fetching from live API")
        return self._fetch_live(settings)

    def _fetch_mock(self) -> list[RawDocument]:
        """Return mock Notion pages."""
        docs = []
        for page in _MOCK_NOTION_PAGES:
            docs.append(
                RawDocument(
                    source="notion",
                    source_id=page["id"],
                    title=page["title"],
                    content=page["content"],
                    url=page["url"],
                    created_at=page["created_time"],
                    updated_at=page["last_edited_time"],
                    tags=page.get("tags", []),
                )
            )
        logger.info("Notion mock: returned %d pages", len(docs))
        return docs

    def _extract_rich_text(self, rich_text: list[dict]) -> str:
        """Extract plain text from Notion rich_text array."""
        return "".join(t.get("plain_text", "") for t in rich_text)

    def _extract_page_content(self, client: Any, page_id: str) -> str:
        """Extract content from a Notion page by iterating its blocks."""
        try:
            blocks = client.blocks.children.list(block_id=page_id)
            content_parts: list[str] = []

            for block in blocks.get("results", []):
                block_type = block.get("type", "")
                block_data = block.get(block_type, {})

                if "rich_text" in block_data:
                    text = self._extract_rich_text(block_data["rich_text"])
                    if text:
                        if block_type.startswith("heading"):
                            level = block_type[-1]
                            content_parts.append(f"{'#' * int(level)} {text}")
                        else:
                            content_parts.append(text)

            return "\n\n".join(content_parts)
        except Exception as e:
            logger.warning("Failed to extract Notion page content", extra={"error": str(e)})
            return ""

    def _fetch_live(self, settings) -> list[RawDocument]:
        """Fetch real pages from Notion API."""
        try:
            from notion_client import Client

            client = Client(auth=settings.notion_api_token)
            docs: list[RawDocument] = []

            # Search all accessible pages
            response = client.search(
                filter={"property": "object", "value": "page"},
                page_size=100,
            )

            for page in response.get("results", []):
                page_id = page["id"]
                title_prop = page.get("properties", {}).get("title", {})
                title = ""
                if "title" in title_prop:
                    title = self._extract_rich_text(title_prop["title"])
                elif "Name" in page.get("properties", {}):
                    title = self._extract_rich_text(
                        page["properties"]["Name"].get("title", [])
                    )

                content = self._extract_page_content(client, page_id)
                if not content:
                    continue

                docs.append(
                    RawDocument(
                        source="notion",
                        source_id=page_id,
                        title=title or page_id,
                        content=f"# {title}\n\n{content}",
                        url=page.get("url", ""),
                        created_at=page.get("created_time", ""),
                        updated_at=page.get("last_edited_time", ""),
                    )
                )

            logger.info("Notion live: fetched %d pages", len(docs))
            return docs

        except Exception as e:
            raise ConnectorError(connector_name="notion", reason=str(e)) from e

    def health_check(self) -> bool:
        """Check Notion API connectivity."""
        settings = get_settings()
        if settings.use_mock_connectors:
            return True
        try:
            from notion_client import Client
            client = Client(auth=settings.notion_api_token)
            client.users.me()
            return True
        except Exception as e:
            logger.warning("Notion health check failed", extra={"error": str(e)})
            return False
