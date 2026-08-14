#!/usr/bin/env python3
"""
scripts/seed_data.py
─────────────────────
Seed Qdrant with sample documents from all mock connectors
for development and testing purposes.

Usage:
    python scripts/seed_data.py
    python scripts/seed_data.py --connector gmail
    python scripts/seed_data.py --clear-first
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logger import configure_logging, get_logger

configure_logging()
logger = get_logger("seed_data")


def seed(connectors: list[str] | None = None, clear_first: bool = False) -> None:
    """Run the ingestion pipeline to seed Qdrant with mock data."""
    from src.core.config import get_settings
    from src.core.vector_store import QdrantVectorStore
    from src.data_ingestion.pipeline import IngestionPipeline
    from src.data_ingestion.connectors import GmailConnector, NotionConnector, JiraConnector

    settings = get_settings()

    print("═══════════════════════════════════════════")
    print("  Agentic RAG — Data Seeder")
    print("═══════════════════════════════════════════\n")
    print(f"Qdrant: {settings.qdrant_host}:{settings.qdrant_port}")
    print(f"Collection: {settings.qdrant_collection_name}")
    print(f"Mock connectors: {settings.use_mock_connectors}\n")

    if clear_first:
        print("🗑️  Clearing existing data...")
        vs = QdrantVectorStore()
        vs.ensure_collection(settings.qdrant_collection_name)
        # Delete all docs
        try:
            vs.delete_collection(settings.qdrant_collection_name)
            vs.ensure_collection(settings.qdrant_collection_name)
            print("✅ Collection cleared and recreated\n")
        except Exception as e:
            print(f"⚠️  Could not clear collection: {e}\n")

    # Select connectors
    connector_map = {
        "gmail": GmailConnector(),
        "notion": NotionConnector(),
        "jira": JiraConnector(),
    }

    selected = []
    if connectors:
        for name in connectors:
            if name in connector_map:
                selected.append(connector_map[name])
                print(f"📡 Selected connector: {name}")
            else:
                print(f"⚠️  Unknown connector: {name}")
    else:
        selected = list(connector_map.values())
        print("📡 Using all connectors: gmail, notion, jira")

    print()

    # Run ingestion
    pipeline = IngestionPipeline(connectors=selected)

    print("🚀 Starting ingestion...")
    summary = pipeline.run_once()

    print("\n📊 Ingestion Summary:")
    print(f"   Connectors run:     {summary['connectors_run']}")
    print(f"   Connectors failed:  {summary['connectors_failed']}")
    print(f"   Documents fetched:  {summary['total_docs_fetched']}")
    print(f"   Chunks ingested:    {summary['total_chunks_ingested']}")

    # Verify by checking collection info
    try:
        vs = QdrantVectorStore()
        info = vs.collection_info(settings.qdrant_collection_name)
        print(f"\n🔍 Qdrant Collection '{settings.qdrant_collection_name}':")
        print(f"   Points:   {info.get('points_count', '?')}")
        print(f"   Vectors:  {info.get('vectors_count', '?')}")
        print(f"   Status:   {info.get('status', '?')}")
    except Exception as e:
        print(f"\n⚠️  Could not verify collection: {e}")

    print("\n✅ Seeding complete!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed Qdrant with sample data from mock connectors",
    )
    parser.add_argument(
        "--connector",
        choices=["gmail", "notion", "jira"],
        action="append",
        help="Specific connector(s) to seed from (default: all)",
    )
    parser.add_argument(
        "--clear-first",
        action="store_true",
        help="Clear existing data before seeding",
    )
    args = parser.parse_args()
    seed(connectors=args.connector, clear_first=args.clear_first)


if __name__ == "__main__":
    main()
