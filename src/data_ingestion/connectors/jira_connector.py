"""
src/data_ingestion/connectors/jira_connector.py
────────────────────────────────────────────────
Jira connector fetching issues, comments, and epics.
Mock mode returns realistic Jira issue data for development.
"""
from __future__ import annotations

from typing import Any

from src.core.config import get_settings
from src.core.exceptions import ConnectorError
from src.data_ingestion.base_connector import BaseConnector, RawDocument
from src.utils.logger import get_logger

logger = get_logger(__name__)


_MOCK_JIRA_ISSUES: list[dict[str, Any]] = [
    {
        "id": "jira_PROJ-101",
        "key": "PROJ-101",
        "summary": "Implement vector search backend with Qdrant",
        "description": (
            "## Summary\n"
            "Integrate Qdrant as the vector database backend to enable semantic search.\n\n"
            "## Acceptance Criteria\n"
            "- Qdrant Docker service configured and running\n"
            "- Documents can be ingested via REST API endpoint\n"
            "- Semantic search returns top-K results with scores\n"
            "- Latency for search < 200ms at P95\n"
            "- Unit tests covering happy path and error cases\n\n"
            "## Technical Notes\n"
            "Use qdrant-client Python SDK. Collection should use COSINE distance.\n"
            "Embedding model: text-embedding-3-small (1536 dimensions).\n"
        ),
        "status": "In Progress",
        "priority": "High",
        "assignee": "Alex Chen",
        "reporter": "Priya Sharma",
        "created": "2026-07-10T09:00:00Z",
        "updated": "2026-07-26T14:30:00Z",
        "labels": ["backend", "search", "ml"],
        "comments": [
            "Alex Chen (2026-07-20): Initial Qdrant setup done. Working on the upsert API.",
            "Priya Sharma (2026-07-22): Reviewed design. Looks good. Proceed.",
        ],
    },
    {
        "id": "jira_PROJ-102",
        "key": "PROJ-102",
        "summary": "Set up Redis for session caching",
        "description": (
            "## Summary\n"
            "Configure Redis as the session cache and rate-limiting backend.\n\n"
            "## Acceptance Criteria\n"
            "- Redis Docker service added to docker-compose.yml\n"
            "- Session data TTL set to 1 hour\n"
            "- Connection pooling configured for production\n"
            "- Health check endpoint returns Redis status\n\n"
            "## Definition of Done\n"
            "- Code reviewed and merged\n"
            "- Deployed to staging\n"
            "- Load test shows no connection errors at 1000 RPS\n"
        ),
        "status": "Done",
        "priority": "Medium",
        "assignee": "Jordan Lee",
        "reporter": "Alex Chen",
        "created": "2026-07-12T10:00:00Z",
        "updated": "2026-07-23T16:00:00Z",
        "labels": ["backend", "infrastructure", "cache"],
        "comments": [
            "Jordan Lee (2026-07-23): Redis configured and deployed. Load tests passed.",
        ],
    },
    {
        "id": "jira_PROJ-103",
        "key": "PROJ-103",
        "summary": "Implement PII redaction in API responses",
        "description": (
            "## Summary\n"
            "Add PII detection and redaction to ensure no personal data leaks "
            "in API responses. Use Microsoft Presidio.\n\n"
            "## Acceptance Criteria\n"
            "- Email addresses redacted in all API responses\n"
            "- Phone numbers redacted\n"
            "- SSN and credit card numbers blocked\n"
            "- Presidio score threshold configurable via YAML\n"
            "- Performance overhead < 50ms per request\n\n"
            "## Security Review\n"
            "Security team must review before deployment. Contact Morgan for approval.\n"
        ),
        "status": "To Do",
        "priority": "High",
        "assignee": "Morgan Wilson",
        "reporter": "Security Team",
        "created": "2026-07-15T09:00:00Z",
        "updated": "2026-07-25T11:00:00Z",
        "labels": ["security", "guardrails", "compliance"],
        "comments": [],
    },
    {
        "id": "jira_PROJ-104",
        "key": "PROJ-104",
        "summary": "Fix P95 latency regression in search API",
        "description": (
            "## Bug Report\n"
            "P95 latency for /api/search spiked from 180ms to 650ms after the v2.3.0 deployment.\n\n"
            "## Root Cause\n"
            "N+1 query problem in the results enrichment step. Each result triggers a separate "
            "database call to fetch author metadata.\n\n"
            "## Fix\n"
            "Batch author metadata lookup using a single IN query. Expected to reduce latency "
            "back to sub-200ms.\n\n"
            "## Priority: P0 - Blocking release\n"
        ),
        "status": "In Progress",
        "priority": "Critical",
        "assignee": "Alex Chen",
        "reporter": "Monitoring Alert",
        "created": "2026-07-26T05:00:00Z",
        "updated": "2026-07-26T09:00:00Z",
        "labels": ["bug", "performance", "p0"],
        "comments": [
            "Alex Chen (2026-07-26): Identified root cause. Fix in progress.",
        ],
    },
]


class JiraConnector(BaseConnector):
    """
    Jira connector fetching issues with descriptions and comments.

    Production setup:
        1. Generate an API token at https://id.atlassian.com/manage-profile/security/api-tokens
        2. Set JIRA_SERVER_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY in .env
        3. Set USE_MOCK_CONNECTORS=false
    """

    @property
    def name(self) -> str:
        return "jira"

    def fetch_documents(self) -> list[RawDocument]:
        """Fetch Jira issues."""
        settings = get_settings()

        if settings.use_mock_connectors:
            logger.info("Jira connector: using mock data")
            return self._fetch_mock()

        logger.info("Jira connector: fetching from live API")
        return self._fetch_live(settings)

    def _issue_to_content(self, issue: dict) -> str:
        """Format a Jira issue dict into rich text content."""
        parts = [
            f"[{issue['key']}] {issue['summary']}",
            f"Status: {issue['status']} | Priority: {issue['priority']}",
            f"Assignee: {issue['assignee']} | Reporter: {issue['reporter']}",
            f"Labels: {', '.join(issue.get('labels', []))}",
            f"Created: {issue['created']} | Updated: {issue['updated']}",
            "",
            "## Description",
            issue.get("description", "No description."),
        ]

        comments = issue.get("comments", [])
        if comments:
            parts.append("\n## Comments")
            parts.extend(f"- {c}" for c in comments)

        return "\n".join(parts)

    def _fetch_mock(self) -> list[RawDocument]:
        """Return mock Jira issue data."""
        docs = []
        for issue in _MOCK_JIRA_ISSUES:
            docs.append(
                RawDocument(
                    source="jira",
                    source_id=issue["id"],
                    title=f"[{issue['key']}] {issue['summary']}",
                    content=self._issue_to_content(issue),
                    created_at=issue["created"],
                    updated_at=issue["updated"],
                    tags=issue.get("labels", []),
                    extra_metadata={
                        "jira_key": issue["key"],
                        "status": issue["status"],
                        "priority": issue["priority"],
                        "assignee": issue["assignee"],
                    },
                )
            )
        logger.info("Jira mock: returned %d issues", len(docs))
        return docs

    def _fetch_live(self, settings) -> list[RawDocument]:
        """Fetch real Jira issues using the Jira REST API."""
        try:
            from jira import JIRA

            jira_client = JIRA(
                server=settings.jira_server_url,
                basic_auth=(settings.jira_email, settings.jira_api_token),
            )

            jql = f"project = {settings.jira_project_key} AND updated >= -1d ORDER BY updated DESC"
            issues = jira_client.search_issues(
                jql,
                maxResults=settings.jira_max_results,
                fields=[
                    "summary", "description", "status", "priority",
                    "assignee", "reporter", "created", "updated", "labels", "comment"
                ],
            )

            docs: list[RawDocument] = []
            for issue in issues:
                fields = issue.fields

                # Extract comments
                comments = []
                if hasattr(fields, "comment") and fields.comment:
                    for comment in fields.comment.comments[:5]:  # Last 5 comments
                        author = comment.author.displayName if comment.author else "Unknown"
                        comments.append(f"{author} ({comment.created[:10]}): {comment.body[:300]}")

                issue_dict = {
                    "key": issue.key,
                    "summary": fields.summary or "",
                    "description": fields.description or "No description.",
                    "status": fields.status.name if fields.status else "Unknown",
                    "priority": fields.priority.name if fields.priority else "Unknown",
                    "assignee": fields.assignee.displayName if fields.assignee else "Unassigned",
                    "reporter": fields.reporter.displayName if fields.reporter else "Unknown",
                    "created": str(fields.created),
                    "updated": str(fields.updated),
                    "labels": [str(label) for label in (fields.labels or [])],
                    "comments": comments,
                }

                docs.append(
                    RawDocument(
                        source="jira",
                        source_id=f"jira_{issue.key}",
                        title=f"[{issue.key}] {issue_dict['summary']}",
                        content=self._issue_to_content(issue_dict),
                        created_at=issue_dict["created"],
                        updated_at=issue_dict["updated"],
                        tags=issue_dict["labels"],
                        extra_metadata={
                            "jira_key": issue.key,
                            "status": issue_dict["status"],
                            "priority": issue_dict["priority"],
                            "assignee": issue_dict["assignee"],
                        },
                    )
                )

            logger.info("Jira live: fetched %d issues", len(docs))
            return docs

        except Exception as e:
            raise ConnectorError(connector_name="jira", reason=str(e)) from e

    def health_check(self) -> bool:
        """Check Jira connectivity."""
        settings = get_settings()
        if settings.use_mock_connectors:
            return True
        try:
            from jira import JIRA
            client = JIRA(
                server=settings.jira_server_url,
                basic_auth=(settings.jira_email, settings.jira_api_token),
            )
            client.myself()
            return True
        except Exception as e:
            logger.warning("Jira health check failed", extra={"error": str(e)})
            return False
