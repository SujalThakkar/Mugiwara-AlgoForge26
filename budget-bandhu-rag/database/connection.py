"""
database/connection.py — Unified database connection module.

Single import point for ALL database connections in BudgetBandhu:
  - SQLite (aiosqlite): Tier 1 working memory only
  - MongoDB Atlas (Motor): Tiers 2-5 and audit logs

ENV:
  SQLITE_PATH        — Path to SQLite file (default: working_memory.db)
  MONGODB_ATLAS_URI  — Atlas connection string
  MONGODB_DATABASE   — Atlas database name (default: budget_bandhu)

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import aiosqlite
from motor.motor_asyncio import AsyncIOMotorDatabase

from database.atlas_client import (
    close_atlas,
    get_database as _get_atlas_database,
    init_atlas,
    ping_atlas,
)

logger = logging.getLogger(__name__)

_SQLITE_PATH = os.getenv("SQLITE_PATH", "working_memory.db")

# ─────────────────────────────────────────────────────────────────────────────
# SQLITE (TIER 1 — WORKING MEMORY)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def get_sqlite_db(
    path: Optional[str] = None,
) -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Context manager for a single aiosqlite connection.

    Used ONLY for Tier 1 (working_memory table) and fallback tables.
    All other tiers use Atlas.

    Args:
        path: SQLite file path. Defaults to SQLITE_PATH env var.

    Yields:
        aiosqlite.Connection with row_factory set to aiosqlite.Row.

    Example:
        >>> async with get_sqlite_db() as conn:
        ...     await conn.execute("SELECT * FROM working_memory WHERE session_id=?", (sid,))
    """
    db_path = path or _SQLITE_PATH
    try:
        conn = await aiosqlite.connect(db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        await conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# ATLAS (TIERS 2-5 + AUDIT)
# ─────────────────────────────────────────────────────────────────────────────

async def get_atlas_db(
    uri: Optional[str] = None,
    db_name: Optional[str] = None,
) -> AsyncIOMotorDatabase:
    """
    Get the Atlas Motor database handle.

    Lazy initialises on first call. Subsequent calls return cached handle.

    Args:
        uri: Override Atlas URI (optional — uses MONGODB_ATLAS_URI env var).
        db_name: Override database name (optional — uses MONGODB_DATABASE env var).

    Returns:
        AsyncIOMotorDatabase ready for Motor async operations.

    Raises:
        RuntimeError: If Atlas is unreachable after retries.

    Example:
        >>> db = await get_atlas_db()
        >>> await db["episodic_memory"].find_one({"user_id": "u1"})
    """
    return await _get_atlas_database(uri=uri, db_name=db_name)


# ─────────────────────────────────────────────────────────────────────────────
# BOOTSTRAP (call once at app startup)
# ─────────────────────────────────────────────────────────────────────────────

async def init_db(
    sqlite_path: Optional[str] = None,
    atlas_uri: Optional[str] = None,
    db_name: Optional[str] = None,
) -> AsyncIOMotorDatabase:
    """
    Bootstrap both SQLite and Atlas connections.

    Call once in FastAPI lifespan startup event.

    Args:
        sqlite_path: Override SQLite file path.
        atlas_uri: Override Atlas URI.
        db_name: Override database name.

    Returns:
        AsyncIOMotorDatabase (Atlas handle for Tiers 2-5).

    Example:
        >>> @asynccontextmanager
        ... async def lifespan(app):
        ...     await init_db()
        ...     yield
        ...     await shutdown_db()
    """
    global _SQLITE_PATH
    if sqlite_path:
        _SQLITE_PATH = sqlite_path

    # Initialise SQLite (just verify the path is writable)
    try:
        async with get_sqlite_db() as conn:
            await conn.execute("SELECT 1")
        logger.info(f"[DB] SQLite ready: {_SQLITE_PATH}")
    except Exception as exc:
        logger.warning(f"[DB] SQLite init warning: {exc}")

    # Initialise Atlas
    try:
        atlas_db = await init_atlas(uri=atlas_uri, db_name=db_name)
        logger.info("[DB] Atlas ready")
        return atlas_db
    except Exception as exc:
        logger.error(f"[DB] Atlas init failed: {exc}. System will use SQLite fallback.")
        raise


async def shutdown_db() -> None:
    """
    Gracefully close all database connections.

    Call in FastAPI lifespan shutdown event.

    Example:
        >>> await shutdown_db()
    """
    await close_atlas()
    logger.info("[DB] All connections closed.")


# ─────────────────────────────────────────────────────────────────────────────
# RE-EXPORTS
# ─────────────────────────────────────────────────────────────────────────────

# Convenience re-exports so callers only need one import
__all__ = [
    "get_sqlite_db",
    "get_atlas_db",
    "init_db",
    "shutdown_db",
    "ping_atlas",
]
