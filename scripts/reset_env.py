#!/usr/bin/env python3
"""
scripts/reset_env.py
─────────────────────
CLI tool to reset Redis and/or Qdrant state for a clean development environment.

Usage:
    python scripts/reset_env.py --clear-redis --clear-qdrant
    python scripts/reset_env.py --user-id user_123 --session-id session_abc
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_settings
from src.utils.logger import configure_logging, get_logger

configure_logging()
logger = get_logger("reset_env")


def clear_redis(user_id: str | None = None, session_id: str | None = None) -> None:
    """Clear Redis state."""
    import redis

    settings = get_settings()
    client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=True,
    )

    try:
        client.ping()
    except redis.ConnectionError:
        print("❌ Cannot connect to Redis. Is it running?")
        return

    if user_id and session_id:
        key = f"session:{user_id}:{session_id}:history"
        deleted = client.delete(key)
        print(f"✅ Redis: Deleted session key '{key}' ({deleted} key(s))")
    elif user_id:
        keys = client.keys(f"session:{user_id}:*")
        if keys:
            client.delete(*keys)
            print(f"✅ Redis: Deleted {len(keys)} key(s) for user '{user_id}'")
        else:
            print(f"ℹ️  Redis: No keys found for user '{user_id}'")
    else:
        # Flush entire DB (dangerous in production!)
        info = client.info("keyspace")
        key_count = client.dbsize()
        client.flushdb()
        print(f"✅ Redis: Flushed {key_count} key(s) from DB {settings.redis_db}")


def clear_qdrant(collection_name: str | None = None) -> None:
    """Clear Qdrant collections."""
    from src.core.vector_store import QdrantVectorStore

    settings = get_settings()
    vs = QdrantVectorStore()

    collections_to_clear = []
    if collection_name:
        collections_to_clear.append(collection_name)
    else:
        collections_to_clear = [
            settings.qdrant_collection_name,
            settings.qdrant_memory_collection,
        ]

    for coll in collections_to_clear:
        try:
            vs.delete_collection(coll)
            print(f"✅ Qdrant: Deleted collection '{coll}'")
            # Recreate empty collection
            vs.ensure_collection(coll)
            print(f"✅ Qdrant: Recreated empty collection '{coll}'")
        except Exception as e:
            print(f"⚠️  Qdrant: Could not reset '{coll}': {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset Redis and/or Qdrant state for development",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full reset of both Redis and Qdrant
  python scripts/reset_env.py --clear-redis --clear-qdrant

  # Reset specific session only
  python scripts/reset_env.py --clear-redis --user-id user_123 --session-id session_abc

  # Reset only Redis for a specific user
  python scripts/reset_env.py --clear-redis --user-id user_123
        """,
    )

    parser.add_argument("--clear-redis", action="store_true", help="Clear Redis state")
    parser.add_argument("--clear-qdrant", action="store_true", help="Clear Qdrant collections")
    parser.add_argument("--user-id", help="Scope Redis clear to specific user")
    parser.add_argument("--session-id", help="Scope Redis clear to specific session")
    parser.add_argument("--collection", help="Specific Qdrant collection to clear")

    args = parser.parse_args()

    if not args.clear_redis and not args.clear_qdrant:
        parser.print_help()
        print("\n❌ No action specified. Use --clear-redis and/or --clear-qdrant")
        sys.exit(1)

    print("═══════════════════════════════════════")
    print("  Agentic RAG — Environment Reset Tool")
    print("═══════════════════════════════════════\n")

    settings = get_settings()
    print(f"Environment: {settings.app_env}")
    print(f"Redis: {settings.redis_host}:{settings.redis_port}")
    print(f"Qdrant: {settings.qdrant_host}:{settings.qdrant_port}\n")

    if settings.is_production:
        confirm = input("⚠️  WARNING: You are in PRODUCTION mode. Are you sure? (yes/no): ")
        if confirm.lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    if args.clear_redis:
        print("🔄 Clearing Redis...")
        clear_redis(user_id=args.user_id, session_id=args.session_id)

    if args.clear_qdrant:
        print("🔄 Clearing Qdrant...")
        clear_qdrant(collection_name=args.collection)

    print("\n✅ Reset complete!")


if __name__ == "__main__":
    main()
