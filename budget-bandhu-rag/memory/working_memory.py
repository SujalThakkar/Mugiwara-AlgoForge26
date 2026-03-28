"""
memory/working_memory.py — Fixed: WorkingMemoryStore has no attribute get_session_items
Uses SQLite for Tier 1 (local, zero latency).
"""
import sqlite3, json, os, logging
from datetime import datetime, timedelta

logger  = logging.getLogger("BudgetBandhu")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "working_memory.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS working_memory (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, session_id, key) ON CONFLICT REPLACE
        )
    """)
    conn.commit()
    return conn


class WorkingMemoryStore:

    def __init__(self, db=None):
        # db arg accepted but ignored — Tier 1 is always SQLite
        self._init_db()

    def _init_db(self):
        try:
            _get_conn().close()
            logger.info("[WORKING] SQLite Tier-1 ready")
        except Exception as e:
            logger.warning(f"[WORKING] Init failed: {e}")

    # ── PUBLIC API ────────────────────────────────────────────
    async def get_state(self, user_id: str, session_id: str) -> dict:
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT key, value FROM working_memory "
                "WHERE user_id=? AND session_id=?",
                (user_id, session_id)
            ).fetchall()
            conn.close()
            return {r["key"]: json.loads(r["value"]) for r in rows}
        except Exception as e:
            logger.warning(f"[WORKING] get_state failed: {e}")
            return {}

    async def update_state(self, user_id: str, session_id: str, data: dict):
        try:
            conn = _get_conn()
            for key, value in data.items():
                conn.execute(
                    "INSERT OR REPLACE INTO working_memory "
                    "(user_id, session_id, key, value, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, session_id, key,
                     json.dumps(value, default=str),
                     datetime.now().isoformat())
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[WORKING] update_state failed: {e}")

    # ── ALIAS FIX: was 'get_session_items' in old code ────────
    async def get_session_items(self, user_id: str, session_id: str) -> dict:
        return await self.get_state(user_id, session_id)

    async def clear_session(self, user_id: str, session_id: str):
        """Called on session boundary — flush significant data to Atlas episodic."""
        try:
            conn = _get_conn()
            conn.execute(
                "DELETE FROM working_memory WHERE user_id=? AND session_id=?",
                (user_id, session_id)
            )
            conn.commit()
            conn.close()
            logger.info(f"[WORKING] Session {session_id} cleared")
        except Exception as e:
            logger.warning(f"[WORKING] clear_session failed: {e}")
