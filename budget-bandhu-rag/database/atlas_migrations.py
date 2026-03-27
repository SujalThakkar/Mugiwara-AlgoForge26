"""
database/atlas_migrations.py — Idempotent Atlas collection + index setup.

Creates all 7 collections with schema validation (where appropriate),
regular MongoDB indexes, and prints status.

Does NOT create Atlas Search / Vector Search indexes — those must be
created via Atlas UI or mongocli (see atlas_index_definitions.py).

Run standalone:
    python -m database.atlas_migrations
    python -m database.atlas_migrations --verify

Author: Financial Cognitive OS Team
Version: 3.0.0
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from database.atlas_client import get_database

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# COLLECTION DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

REGULAR_COLLECTIONS: List[str] = [
    "episodic_memory",
    "semantic_memory",
    "knowledge_graph_edges",
    "procedural_memory",
    "retrieval_audit",
    "user_profiles",
]

TIME_SERIES_COLLECTION = "trajectory_snapshots"
TIME_SERIES_OPTIONS: Dict[str, Any] = {
    "timeseries": {
        "timeField"  : "timestamp",
        "metaField"  : "metadata",
        "granularity": "hours",
    }
}

# Regular MongoDB index specs: (collection, index_key, options)
INDEX_SPECS: List[tuple] = [
    # episodic_memory
    ("episodic_memory",       [("user_id", ASCENDING), ("created_at", DESCENDING)],     {}),
    ("episodic_memory",       [("user_id", ASCENDING), ("decay_score", DESCENDING)],    {}),
    ("episodic_memory",       [("user_id", ASCENDING), ("event_type", ASCENDING)],      {}),
    # semantic_memory
    ("semantic_memory",       [("user_id", ASCENDING), ("memory_type", ASCENDING), ("confirmed_count", DESCENDING)], {}),
    ("semantic_memory",       [("user_id", ASCENDING), ("attribute", ASCENDING)],       {"unique": True, "sparse": True}),
    # knowledge_graph_edges
    ("knowledge_graph_edges", [("user_id", ASCENDING), ("source_node", ASCENDING), ("relationship", ASCENDING)], {}),
    ("knowledge_graph_edges", [("user_id", ASCENDING), ("target_node", ASCENDING)],     {}),
    ("knowledge_graph_edges", [("user_id", ASCENDING), ("source_node", ASCENDING), ("target_node", ASCENDING)],
                              {"unique": True}),
    # procedural_memory
    ("procedural_memory",     [("user_id", ASCENDING), ("strategy_id", ASCENDING)],     {}),
    ("procedural_memory",     [("user_id", ASCENDING), ("trigger_condition.event_type", ASCENDING)], {}),
    ("procedural_memory",     [("user_id", ASCENDING), ("success_rate", DESCENDING)],   {}),
    # retrieval_audit — TTL 90 days
    ("retrieval_audit",       [("created_at", ASCENDING)],   {"expireAfterSeconds": 7_776_000}),
    ("retrieval_audit",       [("user_id", ASCENDING), ("created_at", DESCENDING)],     {}),
    # user_profiles
    ("user_profiles",         [("user_id", ASCENDING)],      {"unique": True}),
]


# ─────────────────────────────────────────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

async def create_all_collections(db: AsyncIOMotorDatabase) -> None:
    """
    Idempotently create all Atlas collections.

    Regular collections: created if not present (MongoDB creates on first insert,
    but explicit creation allows schema validation in future).
    Time series collection: created with time series options — skipped if exists.

    Args:
        db: AsyncIOMotorDatabase handle.

    Example:
        >>> db = await get_database()
        >>> await create_all_collections(db)
    """
    existing = set(await db.list_collection_names())

    for name in REGULAR_COLLECTIONS:
        if name in existing:
            _ok(f"{name} — already exists")
            continue
        try:
            await db.create_collection(name)
            _ok(f"{name} — created")
        except Exception as exc:
            _fail(f"{name} — {exc}")

    # Time series collection
    if TIME_SERIES_COLLECTION in existing:
        _ok(f"{TIME_SERIES_COLLECTION} — already exists (time series)")
    else:
        try:
            await db.create_collection(
                TIME_SERIES_COLLECTION,
                **TIME_SERIES_OPTIONS,
            )
            _ok(f"{TIME_SERIES_COLLECTION} — created (time series)")
        except Exception as exc:
            _fail(f"{TIME_SERIES_COLLECTION} — {exc}")


async def create_all_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Idempotently create all regular MongoDB indexes for every collection.

    NOTE: Atlas Search and Vector Search indexes are NOT created here.
    See atlas_index_definitions.py for those — they require Atlas UI / mongocli.

    Args:
        db: AsyncIOMotorDatabase handle.

    Example:
        >>> await create_all_indexes(db)
    """
    for collection_name, key_spec, options in INDEX_SPECS:
        try:
            col = db[collection_name]
            options.setdefault("background", True)
            await col.create_index(key_spec, **options)
            key_str = ", ".join(f"{k}:{d}" for k, d in key_spec)
            _ok(f"  index [{key_str}] on {collection_name}")
        except Exception as exc:
            # Duplicate key spec is not an error — just skip
            if "already exists" in str(exc).lower() or "IndexKeySpecsConflict" in str(exc):
                pass  # idempotent
            else:
                _fail(f"  index on {collection_name} — {exc}")


async def verify_setup(db: AsyncIOMotorDatabase) -> bool:
    """
    Verify all expected collections exist and are reachable.

    Returns:
        True if all collections present, False otherwise.

    Example:
        >>> ok = await verify_setup(db)
    """
    existing = set(await db.list_collection_names())
    expected = set(REGULAR_COLLECTIONS) | {TIME_SERIES_COLLECTION}
    missing  = expected - existing

    if missing:
        _fail(f"Missing collections: {missing}")
        return False

    _ok(f"All {len(expected)} collections verified")

    # Quick doc count per collection
    for name in sorted(expected):
        try:
            count = await db[name].estimated_document_count()
            print(f"  {name}: {count} documents")
        except Exception:
            pass

    return True


async def run_all_migrations(db: Optional[AsyncIOMotorDatabase] = None) -> None:
    """
    Master migration function — create collections then indexes.

    Args:
        db: Optional pre-supplied database. If None, calls get_database().

    Example:
        >>> await run_all_migrations()
    """
    if db is None:
        db = await get_database()

    print("\n" + "=" * 60)
    print("  BudgetBandhu — Atlas Migration Runner")
    print("=" * 60)

    print("\n[1/2] Creating collections...")
    await create_all_collections(db)

    print("\n[2/2] Creating regular indexes...")
    await create_all_indexes(db)

    print("\n[VERIFY] Checking setup...")
    ok = await verify_setup(db)

    print("\n" + "=" * 60)
    if ok:
        print("  ✅ Atlas migration complete.")
    else:
        print("  ⚠️  Migration completed with warnings (see above).")

    print("\nNEXT STEPS:")
    print("  1. Create Atlas Search indexes via Atlas UI:")
    print("     python -m database.atlas_index_definitions")
    print("  2. Run: python -m database.atlas_migrations --verify")
    print("=" * 60 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)
    logger.warning(f"[ATLAS_MIGRATIONS] {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv()
    logging.basicConfig(level=logging.WARNING)

    async def _main() -> None:
        db = await get_database()
        if "--verify" in sys.argv:
            await verify_setup(db)
        else:
            await run_all_migrations(db)

    asyncio.run(_main())
