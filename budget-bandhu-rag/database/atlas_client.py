"""
database/atlas_client.py — MongoDB Atlas async client singleton.

Motor (async PyMongo) connection with:
  - Exponential backoff retry (3 attempts)
  - M0 Free Tier safe pool sizing (max 50 connections)
  - Health check / ping
  - Environment-driven config

ENV:
  MONGODB_ATLAS_URI  — Atlas connection string (required)
  MONGODB_DATABASE   — Database name (default: budget_bandhu)

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import certifi
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_DB   = "budget_bandhu"
_MAX_POOL     = 50        # M0 free tier: 500 total, but be conservative
_MIN_POOL     = 2
_CONNECT_TIMEOUT_MS  = 5_000   # 5s
_SERVER_TIMEOUT_MS   = 10_000  # 10s
_RETRY_ATTEMPTS      = 3
_RETRY_BASE_DELAY_S  = 1.0

# Module-level singleton
_client: Optional[AsyncIOMotorClient] = None
_db:     Optional[AsyncIOMotorDatabase] = None
_last_ping_time: float = 0.0
_ping_cache_ttl: float = 30.0   # cache health result for 30s
_last_ping_result: Optional[bool] = None


# ─────────────────────────────────────────────────────────────────────────────
# INITIALISATION
# ─────────────────────────────────────────────────────────────────────────────

async def init_atlas(
    uri: Optional[str] = None,
    db_name: Optional[str] = None,
) -> AsyncIOMotorDatabase:
    """
    Initialise the Motor client singleton with retry logic.

    Idempotent — safe to call multiple times; returns cached client.

    Args:
        uri: Atlas connection string. Falls back to MONGODB_ATLAS_URI env var.
        db_name: Database name. Falls back to MONGODB_DATABASE env var.

    Returns:
        AsyncIOMotorDatabase — ready to use.

    Raises:
        RuntimeError: If Atlas is unreachable after all retries.

    Example:
        >>> db = await init_atlas()
        >>> await db.list_collection_names()
    """
    global _client, _db

    if _db is not None:
        return _db

    atlas_uri = uri or os.getenv("MONGODB_ATLAS_URI")
    if not atlas_uri:
        raise RuntimeError(
            "MONGODB_ATLAS_URI is not set. "
            "Add it to your .env file: MONGODB_ATLAS_URI=mongodb+srv://..."
        )

    database_name = db_name or os.getenv("MONGODB_DATABASE", _DEFAULT_DB)

    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            logger.info(f"[ATLAS] Connecting to '{database_name}' (attempt {attempt}/{_RETRY_ATTEMPTS})")

            client = AsyncIOMotorClient(
                atlas_uri,
                maxPoolSize             = _MAX_POOL,
                minPoolSize             = _MIN_POOL,
                connectTimeoutMS        = _CONNECT_TIMEOUT_MS,
                serverSelectionTimeoutMS= _SERVER_TIMEOUT_MS,
                retryWrites             = True,
                retryReads              = True,
                appName                 = "BudgetBandhu-CognitiveOS",
                tlsCAFile               = certifi.where(),
            )

            # Verify connectivity
            await client.admin.command("ping")
            logger.info(f"[ATLAS] ✅ Connected to MongoDB Atlas — database: '{database_name}'")

            _client = client
            _db = client[database_name]
            return _db

        except Exception as exc:
            delay = _RETRY_BASE_DELAY_S * (2 ** (attempt - 1))  # 1s, 2s, 4s
            logger.warning(
                f"[ATLAS] Connection attempt {attempt} failed: {exc}. "
                f"{'Retrying in ' + str(delay) + 's...' if attempt < _RETRY_ATTEMPTS else 'All retries exhausted.'}"
            )
            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(delay)

    raise RuntimeError(
        f"[ATLAS] Cannot connect after {_RETRY_ATTEMPTS} attempts. "
        "Check MONGODB_ATLAS_URI and Atlas network access settings."
    )


def get_client() -> Optional[AsyncIOMotorClient]:
    """Return the Motor client if initialised, else None."""
    return _client


async def get_database(
    uri: Optional[str] = None,
    db_name: Optional[str] = None,
) -> AsyncIOMotorDatabase:
    """
    Get the database handle, initialising if needed.

    Thread-safe singleton access pattern.

    Args:
        uri: Override Atlas URI (optional).
        db_name: Override database name (optional).

    Returns:
        AsyncIOMotorDatabase

    Example:
        >>> db = await get_database()
        >>> await db["episodic_memory"].count_documents({})
    """
    global _db
    if _db is not None:
        return _db
    return await init_atlas(uri=uri, db_name=db_name)


async def ping_atlas() -> bool:
    """
    Non-blocking Atlas health check with 30-second result caching.

    Returns:
        True if Atlas ping succeeds, False otherwise.
        Cached for 30 seconds to avoid hammering the cluster.

    Example:
        >>> is_up = await ping_atlas()
        >>> print("Atlas is UP" if is_up else "Atlas is DOWN — using fallback")
    """
    global _last_ping_time, _last_ping_result

    now = time.monotonic()
    if _last_ping_result is not None and (now - _last_ping_time) < _ping_cache_ttl:
        return _last_ping_result

    if _client is None:
        _last_ping_result = False
        _last_ping_time   = now
        return False

    try:
        await asyncio.wait_for(
            _client.admin.command("ping"),
            timeout=3.0,
        )
        _last_ping_result = True
    except Exception as exc:
        logger.warning(f"[ATLAS] Ping failed: {exc}")
        _last_ping_result = False

    _last_ping_time = time.monotonic()
    return _last_ping_result


def invalidate_ping_cache() -> None:
    """Force next ping_atlas() to perform a live check (skip cache)."""
    global _last_ping_time
    _last_ping_time = 0.0


async def close_atlas() -> None:
    """
    Gracefully close the Motor client.
    Call during application shutdown (e.g., FastAPI lifespan event).
    """
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db     = None
        logger.info("[ATLAS] Client closed.")
