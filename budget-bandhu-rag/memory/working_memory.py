"""
memory/working_memory.py — Tier 1: Session-scoped working memory with TTL eviction.

Holds the "attention window" for an active conversation session.
Auto-evicts stale items. Triggers flush to episodic when token budget exceeded.

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from database.connection import AsyncDBPool
from models.schemas import WorkingMemoryItem

logger = logging.getLogger(__name__)

_MAX_TOKENS       = 2048
_FLUSH_THRESHOLD  = 0.70   # flush when 70% full
_DEFAULT_TTL_MINS = 30


class WorkingMemoryStore:
    """
    Tier 1 memory: lightweight, session-scoped, time-bounded.

    TTL eviction is lazy (checked on every read/write).
    Token counting is approximate: 1 token ≈ 4 characters.
    """

    def __init__(self, pool: AsyncDBPool, max_tokens: int = _MAX_TOKENS):
        self._pool = pool
        self._max_tokens = max_tokens
        self._flush_threshold = int(max_tokens * _FLUSH_THRESHOLD)

    # ──────────────────────────────────────────────────────────────────────────
    # WRITE
    # ──────────────────────────────────────────────────────────────────────────

    async def add(
        self,
        session_id: str,
        user_id: str,
        content_type: str,
        content: dict,
        importance_score: float = 0.5,
        ttl_minutes: int = _DEFAULT_TTL_MINS,
    ) -> WorkingMemoryItem:
        """
        Add an item to working memory for a session.

        Args:
            session_id: Active session identifier.
            user_id: User identifier.
            content_type: One of 'transaction', 'query', 'context_summary', 'active_goal'.
            content: Arbitrary dict payload.
            importance_score: Higher → kept longer during flush prioritisation.
            ttl_minutes: Seconds before auto-eviction.

        Returns:
            The persisted WorkingMemoryItem.

        Example:
            >>> store = WorkingMemoryStore(pool)
            >>> item = await store.add("sess-001", "user-1", "query",
            ...                        {"text": "how much did I spend?"}, importance_score=0.8)
        """
        content_json = json.dumps(content, ensure_ascii=False)
        token_count  = max(1, len(content_json) // 4)

        item = WorkingMemoryItem(
            id               = str(uuid.uuid4()),
            session_id       = session_id,
            user_id          = user_id,
            content_type     = content_type,
            content_json     = content,          # stored as dict in model
            token_count      = token_count,
            importance_score = importance_score,
            expires_at       = datetime.utcnow() + timedelta(minutes=ttl_minutes),
        )

        await self._pool.execute_write(
            """
            INSERT OR REPLACE INTO working_memory
              (id, session_id, user_id, content_type, content_json,
               token_count, created_at, expires_at, importance_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                session_id,
                user_id,
                content_type,
                content_json,
                token_count,
                item.created_at.isoformat(),
                item.expires_at.isoformat() if item.expires_at else None,
                importance_score,
            ),
        )

        return item

    # ──────────────────────────────────────────────────────────────────────────
    # READ
    # ──────────────────────────────────────────────────────────────────────────

    async def get_session(
        self,
        session_id: str,
        content_type: Optional[str] = None,
    ) -> List[WorkingMemoryItem]:
        """
        Retrieve all non-expired working memory items for a session.
        Lazy eviction: expired items are deleted during this call.

        Args:
            session_id: Session to query.
            content_type: Optional filter by type.

        Returns:
            List of WorkingMemoryItem ordered by importance DESC.
        """
        now_iso = datetime.utcnow().isoformat()

        # Lazy eviction
        await self._pool.execute_write(
            "DELETE FROM working_memory WHERE session_id = ? AND expires_at < ?",
            (session_id, now_iso),
        )

        sql = """
            SELECT * FROM working_memory
            WHERE session_id = ?
              AND (expires_at IS NULL OR expires_at > ?)
        """
        params: tuple = (session_id, now_iso)

        if content_type:
            sql += " AND content_type = ?"
            params += (content_type,)

        sql += " ORDER BY importance_score DESC, created_at ASC"

        rows = await self._pool.execute(sql, params)
        return [_row_to_item(r) for r in rows]

    # ──────────────────────────────────────────────────────────────────────────
    # TOKEN BUDGET STATUS
    # ──────────────────────────────────────────────────────────────────────────

    async def token_usage(self, session_id: str) -> dict:
        """
        Returns current token usage for a session.

        Returns:
            {"used": int, "capacity": int, "pct": float, "needs_flush": bool}
        """
        now_iso = datetime.utcnow().isoformat()
        rows = await self._pool.execute(
            """
            SELECT SUM(token_count) AS total FROM working_memory
            WHERE session_id = ? AND (expires_at IS NULL OR expires_at > ?)
            """,
            (session_id, now_iso),
        )
        used = rows[0].get("total") or 0 if rows else 0
        return {
            "used": used,
            "capacity": self._max_tokens,
            "pct": used / self._max_tokens,
            "needs_flush": used >= self._flush_threshold,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # EVICTION
    # ──────────────────────────────────────────────────────────────────────────

    async def clear_session(self, session_id: str) -> int:
        """Hard-delete all working memory for a session. Returns rows deleted."""
        async with self._pool.acquire() as db:
            cursor = await db.execute(
                "DELETE FROM working_memory WHERE session_id = ?", (session_id,)
            )
            await db.commit()
            deleted = cursor.rowcount
        logger.info(f"[WORKING MEM] Cleared {deleted} items for session {session_id}")
        return deleted

    async def get_candidates_for_flush(
        self, session_id: str, token_budget: int = 600
    ) -> List[WorkingMemoryItem]:
        """
        Returns the least-important items that sum to ≤ token_budget.
        These are candidates to be summarised and evicted during flush.
        """
        all_items = await self.get_session(session_id)
        # Sort ascending by importance (evict weakest first)
        all_items.sort(key=lambda x: x.importance_score)

        candidates: list[WorkingMemoryItem] = []
        tokens_collected = 0
        for item in all_items:
            if tokens_collected >= token_budget:
                break
            candidates.append(item)
            tokens_collected += item.token_count

        return candidates

    async def delete_items(self, item_ids: List[str]) -> None:
        """Remove specific items by ID after flush."""
        if not item_ids:
            return
        placeholders = ",".join("?" * len(item_ids))
        await self._pool.execute_write(
            f"DELETE FROM working_memory WHERE id IN ({placeholders})",
            tuple(item_ids),
        )


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_item(row: dict) -> WorkingMemoryItem:
    content = row["content_json"]
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except Exception:
            content = {"raw": content}

    return WorkingMemoryItem(
        id               = row["id"],
        session_id       = row["session_id"],
        user_id          = row["user_id"],
        content_type     = row["content_type"],
        content_json     = content,
        token_count      = row.get("token_count", 0),
        created_at       = _parse_dt(row.get("created_at")),
        expires_at       = _parse_dt(row.get("expires_at")),
        importance_score = row.get("importance_score", 0.5),
    )


def _parse_dt(val) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None
