"""
database/migrations.py — Master migration runner: SQLite + Atlas.

Runs at startup to guarantee schema consistency across both stores.

Responsibilities:
  1. Create SQLite tables (working_memory, fallback tables) — idempotent
  2. Trigger Atlas collection + index creation
  3. Provide migrate_sqlite_to_atlas() for one-time data migration

Run standalone:
    python -m database.migrations
    python -m database.migrations --user <user_id>   # migrate specific user

Author: Financial Cognitive OS Team
Version: 3.0.0
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import List, Optional

import aiosqlite

logger = logging.getLogger(__name__)

_SQLITE_PATH = os.getenv("SQLITE_PATH", "working_memory.db")

# ─────────────────────────────────────────────────────────────────────────────
# SQLITE SCHEMA  (Tier 1 + fallback tables only)
# ─────────────────────────────────────────────────────────────────────────────

_SQLITE_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Tier 1: Working Memory (stays in SQLite permanently)
CREATE TABLE IF NOT EXISTS working_memory (
    id               TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    content_type     TEXT NOT NULL,
    content_json     TEXT NOT NULL,
    token_count      INTEGER DEFAULT 0,
    importance_score REAL DEFAULT 0.5,
    created_at       TEXT NOT NULL,
    expires_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_wm_session ON working_memory(session_id, user_id);
CREATE INDEX IF NOT EXISTS idx_wm_expires ON working_memory(expires_at);

-- Session metadata
CREATE TABLE IF NOT EXISTS session_metadata (
    session_id    TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    last_active   TEXT NOT NULL,
    turn_count    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sm_user ON session_metadata(user_id);

-- Episodic fallback (read-only mirror, no embeddings, capped 50/user)
CREATE TABLE IF NOT EXISTS episodic_fallback (
    id                   TEXT PRIMARY KEY,
    user_id              TEXT NOT NULL,
    event_type           TEXT NOT NULL,
    trigger_description  TEXT NOT NULL,
    outcome_description  TEXT NOT NULL DEFAULT '',
    category             TEXT,
    amount_inr           REAL,
    decay_score          REAL DEFAULT 1.0,
    confidence_score     REAL DEFAULT 0.5,
    created_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ef_user_decay
    ON episodic_fallback(user_id, decay_score DESC);

-- Semantic fallback (no embeddings)
CREATE TABLE IF NOT EXISTS semantic_fallback (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    memory_type      TEXT NOT NULL,
    attribute        TEXT NOT NULL,
    value            TEXT NOT NULL,
    confidence_score REAL DEFAULT 0.5,
    confirmed_count  INTEGER DEFAULT 0,
    last_updated     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sf_user_attr
    ON semantic_fallback(user_id, attribute);

-- Migration tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    version    TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL
);
"""


async def run_sqlite_migrations(sqlite_path: Optional[str] = None) -> None:
    """
    Apply all SQLite DDL statements idempotently.

    Args:
        sqlite_path: Override path (default: SQLITE_PATH env var).

    Example:
        >>> await run_sqlite_migrations()
    """
    path = sqlite_path or _SQLITE_PATH
    try:
        async with aiosqlite.connect(path) as conn:
            await conn.executescript(_SQLITE_DDL)
            await conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?,?)",
                ("v3.0.0-hybrid", datetime.utcnow().isoformat()),
            )
            await conn.commit()
        logger.info(f"[MIGRATIONS] SQLite schema ready: {path}")
        print(f"  ✓  SQLite schema ready ({path})")
    except Exception as exc:
        logger.error(f"[MIGRATIONS] SQLite migration failed: {exc}")
        print(f"  ✗  SQLite migration failed: {exc}", file=sys.stderr)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# ATLAS MIGRATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def run_atlas_migrations() -> None:
    """
    Trigger Atlas collection + index creation via atlas_migrations module.

    Gracefully skips if Atlas is unreachable (system will use fallback).

    Example:
        >>> await run_atlas_migrations()
    """
    try:
        from database.atlas_client import get_database
        from database.atlas_migrations import run_all_migrations
        db = await get_database()
        await run_all_migrations(db)
    except Exception as exc:
        logger.warning(f"[MIGRATIONS] Atlas setup skipped (will use fallback): {exc}")
        print(f"  ⚠️  Atlas setup skipped: {exc}")
        print("     System will operate in SQLite-only fallback mode.")


# ─────────────────────────────────────────────────────────────────────────────
# ONE-TIME DATA MIGRATION: SQLite → Atlas
# ─────────────────────────────────────────────────────────────────────────────

async def migrate_sqlite_to_atlas(
    user_id: str,
    sqlite_path: Optional[str] = None,
    batch_size: int = 50,
) -> None:
    """
    One-time migration of existing user data from old SQLite episodic/semantic
    tables to Atlas.

    Safe to run multiple times — uses upsert (no duplicates).
    Embeds text using sentence-transformers if available.

    Args:
        user_id: User whose data to migrate.
        sqlite_path: Old SQLite database path (default: SQLITE_PATH env var).
        batch_size: Records per batch (respect M0 write limits).

    Example:
        >>> await migrate_sqlite_to_atlas("user-123")
    """
    path = sqlite_path or _SQLITE_PATH
    migrated_ep = 0
    migrated_sm = 0

    try:
        from database.atlas_client import get_database
        db = await get_database()
    except Exception as exc:
        logger.error(f"[MIGRATE] Cannot connect to Atlas: {exc}")
        print(f"  ✗  Cannot connect to Atlas for migration: {exc}")
        return

    # Lazy-load embedder
    embedder = _load_embedder()

    # ── Migrate episodic_memory ───────────────────────────────────────────────
    try:
        async with aiosqlite.connect(path) as conn:
            conn.row_factory = aiosqlite.Row
            try:
                cursor = await conn.execute(
                    "SELECT * FROM episodic_memory WHERE user_id = ? ORDER BY created_at",
                    (user_id,),
                )
                rows = await cursor.fetchall()
            except aiosqlite.OperationalError:
                rows = []   # Table doesn't exist in new installs

        if rows:
            print(f"  [MIGRATE] Migrating {len(rows)} episodic records for {user_id}...")
            col = db["episodic_memory"]
            batch: List[dict] = []
            for row in rows:
                doc = dict(row)
                doc.pop("id", None)   # Let Atlas use its own _id
                if embedder and doc.get("trigger_description"):
                    text = f"{doc['trigger_description']} {doc.get('outcome_description','')}"
                    doc["embedding"] = embedder.encode(text, normalize_embeddings=True).tolist()
                doc["_migrated_from_sqlite"] = True
                batch.append(doc)
                if len(batch) >= batch_size:
                    await _upsert_batch(col, batch, "id")
                    migrated_ep += len(batch)
                    batch = []
                    await asyncio.sleep(0.1)  # Rate limit
            if batch:
                await _upsert_batch(col, batch, "id")
                migrated_ep += len(batch)
            print(f"  ✓  Migrated {migrated_ep} episodic records")

    except Exception as exc:
        logger.error(f"[MIGRATE] Episodic migration failed: {exc}")
        print(f"  ✗  Episodic migration error: {exc}")
        return  # Don't proceed to semantic if episodic failed

    # ── Migrate semantic_memory ───────────────────────────────────────────────
    try:
        async with aiosqlite.connect(path) as conn:
            conn.row_factory = aiosqlite.Row
            try:
                cursor = await conn.execute(
                    "SELECT * FROM semantic_memory WHERE user_id = ?",
                    (user_id,),
                )
                rows = await cursor.fetchall()
            except aiosqlite.OperationalError:
                rows = []

        if rows:
            print(f"  [MIGRATE] Migrating {len(rows)} semantic records for {user_id}...")
            col = db["semantic_memory"]
            batch = []
            for row in rows:
                doc = dict(row)
                doc.pop("id", None)
                if embedder and doc.get("value"):
                    doc["embedding"] = embedder.encode(
                        f"{doc['attribute']} {doc['value']}",
                        normalize_embeddings=True,
                    ).tolist()
                doc["_migrated_from_sqlite"] = True
                batch.append(doc)
                if len(batch) >= batch_size:
                    await _upsert_batch(col, batch, "attribute")
                    migrated_sm += len(batch)
                    batch = []
                    await asyncio.sleep(0.1)
            if batch:
                await _upsert_batch(col, batch, "attribute")
                migrated_sm += len(batch)
            print(f"  ✓  Migrated {migrated_sm} semantic records")

    except Exception as exc:
        logger.error(f"[MIGRATE] Semantic migration failed (episodic already done): {exc}")
        print(f"  ✗  Semantic migration error: {exc}")

    print(
        f"\n  Migration complete for user '{user_id}':\n"
        f"    Episodic: {migrated_ep} records\n"
        f"    Semantic: {migrated_sm} records"
    )


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

async def _upsert_batch(col, docs: List[dict], unique_key: str) -> None:
    """Upsert a batch of documents into an Atlas collection."""
    from pymongo import UpdateOne
    ops = [
        UpdateOne(
            {"user_id": doc["user_id"], unique_key: doc[unique_key]},
            {"$setOnInsert": doc},
            upsert=True,
        )
        for doc in docs
        if doc.get(unique_key)
    ]
    if ops:
        await col.bulk_write(ops, ordered=False)


def _load_embedder():
    """Lazy-load sentence-transformers embedder."""
    try:
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        return SentenceTransformer(model_name)
    except ImportError:
        logger.warning("[MIGRATE] sentence-transformers not installed — migrating without embeddings")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MASTER RUNNER
# ─────────────────────────────────────────────────────────────────────────────

async def run_all(sqlite_path: Optional[str] = None) -> None:
    """Run SQLite + Atlas migrations together."""
    print("\n" + "=" * 60)
    print("  BudgetBandhu — Database Migration Runner")
    print("=" * 60)
    print("\n[1/2] SQLite migrations...")
    await run_sqlite_migrations(sqlite_path)
    print("\n[2/2] Atlas migrations...")
    await run_atlas_migrations()
    print("\n✅  All migrations complete.\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)

    async def _main() -> None:
        args = sys.argv[1:]
        if "--user" in args:
            idx = args.index("--user")
            user_id = args[idx + 1]
            print(f"\nMigrating SQLite → Atlas for user: {user_id}")
            await migrate_sqlite_to_atlas(user_id)
        else:
            await run_all()

    asyncio.run(_main())
