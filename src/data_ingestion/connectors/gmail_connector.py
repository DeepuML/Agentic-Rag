"""
src/data_ingestion/connectors/gmail_connector.py
─────────────────────────────────────────────────
Gmail data connector. 
- Production mode: Uses Google Gmail API with OAuth2.
- Mock mode: Returns realistic dummy email data for development.

Set USE_MOCK_CONNECTORS=true in .env for mock mode.
"""
from __future__ import annotations

import html
import re
from typing import Any

from src.core.config import get_settings
from src.core.exceptions import ConnectorError
from src.data_ingestion.base_connector import BaseConnector, RawDocument
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Mock Data ─────────────────────────────────────────────────────────────────

_MOCK_EMAILS: list[dict[str, Any]] = [
    {
        "id": "gmail_001",
        "subject": "Q3 Project Status Update - Action Required",
        "body": (
            "Hi team,\n\nPlease find attached the Q3 status update for Project Athena. "
            "We are currently 80% complete on the backend API. The main blocker is the "
            "authentication integration with the SSO provider. Alex needs to review the "
            "OAuth2 configuration by end of week.\n\n"
            "Key milestones:\n"
            "- API endpoints: 90% done\n"
            "- Database migrations: Complete\n"
            "- Frontend integration: 60% done\n"
            "- Testing: Scheduled for next sprint\n\n"
            "Please reply with any blockers by Thursday.\n\nBest regards,\nPriya"
        ),
        "sender": "priya@company.com",
        "date": "2026-07-25T09:15:00Z",
        "thread_id": "thread_q3_001",
        "labels": ["INBOX", "IMPORTANT"],
    },
    {
        "id": "gmail_002",
        "subject": "Meeting Notes: Architecture Review 2026-07-24",
        "body": (
            "Architecture Review Meeting Notes\n"
            "Date: July 24, 2026\n"
            "Attendees: Alex, Priya, Jordan, Morgan\n\n"
            "Key decisions:\n"
            "1. Adopted microservices architecture for the payment module.\n"
            "2. Redis will be used for session caching with a 1-hour TTL.\n"
            "3. PostgreSQL chosen over MongoDB for relational data requirements.\n"
            "4. API gateway: Kong selected over custom solution.\n\n"
            "Action items:\n"
            "- Alex: Set up Kong configuration by Monday\n"
            "- Jordan: Design ERD for payment tables\n"
            "- Morgan: Research Redis Cluster vs Sentinel\n\n"
            "Next meeting: August 1, 2026"
        ),
        "sender": "alex@company.com",
        "date": "2026-07-24T16:30:00Z",
        "thread_id": "thread_arch_001",
        "labels": ["INBOX"],
    },
    {
        "id": "gmail_003",
        "subject": "Urgent: Production Incident - API Latency Spike",
        "body": (
            "INCIDENT REPORT - P1\n\n"
            "Time: 2026-07-26 03:15 UTC\n"
            "Duration: 47 minutes\n"
            "Affected: Search API endpoints\n\n"
            "Root Cause: A misconfigured database connection pool caused connection exhaustion "
            "under load. Max connections were set to 10 instead of 100.\n\n"
            "Resolution: Updated connection pool configuration and deployed hotfix v2.3.1. "
            "Monitoring shows latency returned to normal within 5 minutes of fix.\n\n"
            "Follow-up: Adding connection pool metrics to Grafana dashboard. "
            "Adding alert for connection_pool_utilization > 80%.\n\n"
            "Incident Commander: Jordan"
        ),
        "sender": "oncall@company.com",
        "date": "2026-07-26T04:02:00Z",
        "thread_id": "thread_incident_001",
        "labels": ["INBOX", "IMPORTANT"],
    },
]


class GmailConnector(BaseConnector):
    """
    Gmail connector that fetches emails and converts them to RawDocuments.

    Production setup:
        1. Create OAuth2 credentials in Google Cloud Console
        2. Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN in .env
        3. Set USE_MOCK_CONNECTORS=false in .env
    """

    @property
    def name(self) -> str:
        return "gmail"

    def fetch_documents(self) -> list[RawDocument]:
        """Fetch emails from Gmail (or mock data)."""
        settings = get_settings()

        if settings.use_mock_connectors:
            logger.info("Gmail connector: using mock data")
            return self._fetch_mock()

        logger.info("Gmail connector: fetching from live API")
        return self._fetch_live(settings)

    def _fetch_mock(self) -> list[RawDocument]:
        """Return mock email data."""
        docs = []
        for email in _MOCK_EMAILS:
            docs.append(
                RawDocument(
                    source="gmail",
                    source_id=email["id"],
                    title=email["subject"],
                    content=f"Subject: {email['subject']}\nFrom: {email['sender']}\n\n{email['body']}",
                    author=email["sender"],
                    created_at=email["date"],
                    updated_at=email["date"],
                    extra_metadata={
                        "thread_id": email["thread_id"],
                        "labels": ",".join(email.get("labels", [])),
                    },
                )
            )
        logger.info("Gmail mock: returned %d emails", len(docs))
        return docs

    def _fetch_live(self, settings) -> list[RawDocument]:
        """Fetch real emails using the Gmail API."""
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            import base64

            creds = Credentials(
                token=None,
                refresh_token=settings.gmail_refresh_token,
                client_id=settings.gmail_client_id,
                client_secret=settings.gmail_client_secret,
                token_uri="https://oauth2.googleapis.com/token",
            )

            service = build("gmail", "v1", credentials=creds)

            # List messages
            results = service.users().messages().list(
                userId="me",
                q=settings.configs_dir,  # Uses config search query
                maxResults=settings.gmail_max_results,
            ).execute()

            messages = results.get("messages", [])
            docs = []

            for msg_ref in messages:
                msg = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="full",
                ).execute()

                headers = {
                    h["name"].lower(): h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }

                # Extract body
                body = self._extract_body(msg.get("payload", {}))

                docs.append(
                    RawDocument(
                        source="gmail",
                        source_id=msg["id"],
                        title=headers.get("subject", "No Subject"),
                        content=body,
                        author=headers.get("from", ""),
                        created_at=headers.get("date", ""),
                        updated_at=headers.get("date", ""),
                        extra_metadata={"thread_id": msg.get("threadId", "")},
                    )
                )

            logger.info("Gmail live: fetched %d emails", len(docs))
            return docs

        except Exception as e:
            raise ConnectorError(connector_name="gmail", reason=str(e)) from e

    def _extract_body(self, payload: dict) -> str:
        """Extract text body from Gmail message payload."""
        import base64

        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            result = self._extract_body(part)
            if result:
                return result
        return ""

    def health_check(self) -> bool:
        """Check Gmail connectivity (returns True in mock mode)."""
        settings = get_settings()
        if settings.use_mock_connectors:
            return True
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials(
                token=None,
                refresh_token=settings.gmail_refresh_token,
                client_id=settings.gmail_client_id,
                client_secret=settings.gmail_client_secret,
                token_uri="https://oauth2.googleapis.com/token",
            )
            service = build("gmail", "v1", credentials=creds)
            service.users().getProfile(userId="me").execute()
            return True
        except Exception as e:
            logger.warning("Gmail health check failed", extra={"error": str(e)})
            return False
