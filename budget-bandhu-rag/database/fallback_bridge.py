"""
database/fallback_bridge.py — Atlas → SQLite automatic failover bridge.

When Atlas is unreachable, this bridge:
  1. Detects the failure (non-blocking, 3s timeout)
  2. Routes reads to local SQLite fallback tables (read-only, no vector search)
  3. Buffers writes to an in-memory queue
  4. Drains the write queue to Atlas when connectivity recovers
  5. Logs all fallback operations clearly

SQLite fallback tables (created by database/migrations.py):
  episodic_fallback   — last 50 episodes per user (row-based, no embeddings)
  semantic_fallback   — all semantic facts per user (no embeddings)

Fallback mode LIMITATIONS (logged on activation):
  - No vector similarity search (embedding search unavailable)
  - No knowledge graph traversal (no $graphLookup)
  - No trajectory snapshots (no time series read)
  - BM25 text search replaced by SQL LIKE matching

Author: Financial Cognitive OS Team
Version: 3.0.0
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

import aiosqlite

from database.atlas_client import ping_atlas, invalidate_ping_cache

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# WRITE BUFFER
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BufferedWrite:
    """A write operation deferred during Atlas downtime."""
    collection  : str
    operation   : str           # "insert" | "update" | "upsert"
    document    : Dict[str, Any]
    filter_key  : Optional[Dict[str, Any]] = None
    created_at  : float = field(default_factory=time.monotonic)


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK BRIDGE
# ─────────────────────────────────────────────────────────────────────────────

class AtlasFallbackBridge:
    """
    Automatic failover bridge between Atlas and SQLite.

    State machine:
      ATLAS_UP   → healthy, all operations go to Atlas
      ATLAS_DOWN → fallback mode, reads from SQLite, writes buffered

    Usage:
        bridge = AtlasFallbackBridge(sqlite_path="working_memory.db")
        await bridge.start()

        # Check before any Atlas operation:
        if await bridge.is_atlas_healthy():
            result = await atlas_collection.find(...)
        else:
            result = await bridge.fallback_episodic_read(user_id)
    """

    def __init__(self, sqlite_path: str = "working_memory.db"):
        self._sqlite_path     = sqlite_path
        self._in_fallback     = False
        self._write_buffer    : Deque[BufferedWrite] = deque(maxlen=500)
        self._health_check_interval = 30.0   # seconds
        self._drain_task: Optional[asyncio.Task] = None
        self._recovery_task: Optional[asyncio.Task] = None

    # ──────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ──────────────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start background recovery checker. Call once on app startup."""
        self._recovery_task = asyncio.create_task(self._recovery_loop())
        logger.info("[FALLBACK] Bridge started — monitoring Atlas health")

    async def stop(self) -> None:
        """Cancel background tasks on shutdown."""
        if self._recovery_task:
            self._recovery_task.cancel()
        if self._drain_task:
            self._drain_task.cancel()

    # ──────────────────────────────────────────────────────────────────────────
    # HEALTH CHECK
    # ──────────────────────────────────────────────────────────────────────────

    async def is_atlas_healthy(self) -> bool:
        """
        Non-blocking Atlas health check.
        Uses cached result (30s TTL) so this is safe to call on every request.

        Returns:
            True if Atlas is reachable, False if in fallback mode.

        Example:
            >>> if not await bridge.is_atlas_healthy():
            ...     data = await bridge.fallback_episodic_read(user_id)
        """
        return await ping_atlas()

    # ──────────────────────────────────────────────────────────────────────────
    # FAILOVER CONTROL
    # ──────────────────────────────────────────────────────────────────────────

    async def switch_to_fallback(self, reason: str = "Atlas unreachable") -> None:
        """
        Activate SQLite fallback mode.

        Logs limitations. Does not interrupt in-flight reads.
        Safe to call multiple times (idempotent).

        Args:
            reason: Human-readable reason for switching.

        Example:
            >>> await bridge.switch_to_fallback("Atlas connection timeout after 3s")
        """
        if self._in_fallback:
            return

        self._in_fallback = True
        invalidate_ping_cache()

        logger.warning(
            f"[FALLBACK] ⚠️  SWITCHING TO SQLITE FALLBACK MODE\n"
            f"  Reason: {reason}\n"
            f"  Limitations:\n"
            f"    - No vector similarity search (embeddings unavailable)\n"
            f"    - No knowledge graph traversal ($graphLookup unavailable)\n"
            f"    - No trajectory snapshots (time series unavailable)\n"
            f"    - BM25 replaced by SQL LIKE search\n"
            f"  Writes buffered (max 500). Will drain to Atlas on recovery."
        )

    async def switch_to_atlas(self) -> None:
        """
        Deactivate fallback mode and drain buffered writes to Atlas.

        Called automatically by _recovery_loop() when ping succeeds.

        Example:
            >>> await bridge.switch_to_atlas()
        """
        if not self._in_fallback:
            return

        logger.info("[FALLBACK] ✅ Atlas recovered — switching back from SQLite fallback")
        self._in_fallback = False

        if self._write_buffer:
            logger.info(f"[FALLBACK] Draining {len(self._write_buffer)} buffered writes to Atlas...")
            self._drain_task = asyncio.create_task(self._drain_write_buffer())

    # ──────────────────────────────────────────────────────────────────────────
    # WRITE BUFFERING
    # ──────────────────────────────────────────────────────────────────────────

    def buffer_write(
        self,
        collection: str,
        operation: str,
        document: Dict[str, Any],
        filter_key: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Buffer a write operation for later replay to Atlas.

        Args:
            collection: Atlas collection name.
            operation: "insert" | "update" | "upsert"
            document: Document to write.
            filter_key: For update/upsert — the filter document.

        Example:
            >>> bridge.buffer_write(
            ...     "episodic_memory", "insert",
            ...     {"user_id": "u1", "event_type": "OVERSPEND", ...}
            ... )
        """
        write = BufferedWrite(
            collection = collection,
            operation  = operation,
            document   = document,
            filter_key = filter_key,
        )
        self._write_buffer.append(write)
        logger.debug(f"[FALLBACK] Buffered {operation} to {collection} ({len(self._write_buffer)} queued)")

    async def _drain_write_buffer(self) -> None:
        """Replay buffered writes to Atlas. Runs as background task after recovery."""
        from database.atlas_client import get_database

        try:
            db        = await get_database()
            drained   = 0
            failed    = 0

            while self._write_buffer:
                write = self._write_buffer.popleft()
                try:
                    col = db[write.collection]
                    if write.operation == "insert":
                        await col.insert_one(write.document)
                    elif write.operation == "update" and write.filter_key:
                        await col.update_one(write.filter_key, {"$set": write.document})
                    elif write.operation == "upsert" and write.filter_key:
                        await col.update_one(
                            write.filter_key,
                            {"$set": write.document},
                            upsert=True,
                        )
                    drained += 1
                    await asyncio.sleep(0.01)   # Rate limit — respect M0 limits
                except Exception as exc:
                    logger.warning(f"[FALLBACK] Failed to drain write: {exc}")
                    failed += 1

            logger.info(f"[FALLBACK] Write drain complete — {drained} OK, {failed} failed")

        except Exception as exc:
            logger.error(f"[FALLBACK] Drain task failed: {exc}")

    # ──────────────────────────────────────────────────────────────────────────
    # RECOVERY LOOP
    # ──────────────────────────────────────────────────────────────────────────

    async def _recovery_loop(self) -> None:
        """Background task: check Atlas health every 30s and switch back when healthy."""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                if self._in_fallback:
                    invalidate_ping_cache()
                    healthy = await ping_atlas()
                    if healthy:
                        await self.switch_to_atlas()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug(f"[FALLBACK] Recovery loop error: {exc}")

    # ──────────────────────────────────────────────────────────────────────────
    # FALLBACK READS FROM SQLITE
    # ──────────────────────────────────────────────────────────────────────────

    async def fallback_episodic_read(
        self,
        user_id: str,
        limit: int = 10,
        query_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Read episodic memories from SQLite fallback table.

        No vector search — SQL LIKE used if query_text provided.
        Returns list of dicts compatible with EpisodicMemory schema.

        Args:
            user_id: User to fetch memories for.
            limit: Maximum records to return.
            query_text: Optional keyword search string (SQL LIKE).

        Returns:
            List of episodic memory dicts (without embeddings).

        Example:
            >>> eps = await bridge.fallback_episodic_read("user-1", limit=5)
        """
        try:
            async with aiosqlite.connect(self._sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row

                if query_text:
                    pattern = f"%{query_text}%"
                    cursor = await conn.execute(
                        """SELECT * FROM episodic_fallback
                           WHERE user_id = ?
                             AND (trigger_description LIKE ? OR outcome_description LIKE ?)
                           ORDER BY created_at DESC LIMIT ?""",
                        (user_id, pattern, pattern, limit),
                    )
                else:
                    cursor = await conn.execute(
                        """SELECT * FROM episodic_fallback
                           WHERE user_id = ?
                           ORDER BY decay_score DESC, created_at DESC LIMIT ?""",
                        (user_id, limit),
                    )

                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

        except Exception as exc:
            logger.error(f"[FALLBACK] SQLite episodic read failed: {exc}")
            return []

    async def fallback_semantic_read(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Read semantic facts from SQLite fallback table.

        Args:
            user_id: User to fetch profile for.
            limit: Maximum records to return.

        Returns:
            List of semantic memory dicts.

        Example:
            >>> facts = await bridge.fallback_semantic_read("user-1")
        """
        try:
            async with aiosqlite.connect(self._sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(
                    """SELECT * FROM semantic_fallback
                       WHERE user_id = ?
                       ORDER BY confirmed_count DESC, confidence_score DESC LIMIT ?""",
                    (user_id, limit),
                )
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

        except Exception as exc:
            logger.error(f"[FALLBACK] SQLite semantic read failed: {exc}")
            return []

    async def fallback_write_episodic(self, record: Dict[str, Any]) -> None:
        """
        Write an episodic memory to SQLite fallback table during downtime.

        Capped to 50 records per user (oldest purged on overflow).

        Args:
            record: Episodic memory dict.
        """
        try:
            async with aiosqlite.connect(self._sqlite_path) as conn:
                await conn.execute(
                    """INSERT OR REPLACE INTO episodic_fallback
                       (id, user_id, event_type, trigger_description,
                        outcome_description, category, amount_inr,
                        decay_score, confidence_score, created_at)
                       VALUES (:id,:user_id,:event_type,:trigger_description,
                               :outcome_description,:category,:amount_inr,
                               :decay_score,:confidence_score,:created_at)""",
                    record,
                )
                # Enforce per-user cap of 50 rows
                await conn.execute(
                    """DELETE FROM episodic_fallback
                       WHERE user_id = ? AND id NOT IN (
                           SELECT id FROM episodic_fallback
                           WHERE user_id = ?
                           ORDER BY created_at DESC LIMIT 50
                       )""",
                    (record["user_id"], record["user_id"]),
                )
                await conn.commit()
        except Exception as exc:
            logger.warning(f"[FALLBACK] SQLite episodic write failed: {exc}")

    # ──────────────────────────────────────────────────────────────────────────
    # PROPERTIES
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def in_fallback_mode(self) -> bool:
        """True if currently operating in SQLite fallback mode."""
        return self._in_fallback

    @property
    def buffered_writes_count(self) -> int:
        """Number of writes queued for Atlas drain."""
        return len(self._write_buffer)
