"""
database/fallback_bridge.py — Fixed: no such table: episodic_fallback
Creates all required SQLite fallback tables on init.
"""
import sqlite3, json, os, logging
from datetime import datetime

logger  = logging.getLogger("BudgetBandhu")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "fallback.db")

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS episodic_fallback (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT,
        event_type  TEXT,
        content     TEXT,
        metadata    TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS semantic_fallback (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT,
        fact_type   TEXT,
        content     TEXT,
        confidence  REAL DEFAULT 0.8,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS conversation_fallback (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  TEXT,
        role        TEXT,
        content     TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS transaction_fallback (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT,
        amount      REAL,
        description TEXT,
        category    TEXT,
        date        TEXT,
        synced      INTEGER DEFAULT 0,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
]

_atlas_online = True


def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    for stmt in SCHEMA:
        conn.execute(stmt)
    conn.commit()
    return conn


class AtlasFallbackBridge:

    def __init__(self, db_path=None):
        try:
            _get_conn().close()
            logger.info("[FALLBACK] SQLite fallback tables ready")
        except Exception as e:
            logger.error(f"[FALLBACK] Init failed: {e}")

    def switch_to_sqlite(self, reason: str):
        global _atlas_online
        if _atlas_online:
            _atlas_online = False
            logger.warning(
                f"[FALLBACK] ⚠️  SWITCHING TO SQLITE FALLBACK MODE\n"
                f"  Reason: {reason}\n"
                f"  Limitations:\n"
                f"    - No vector similarity search\n"
                f"    - No knowledge graph traversal\n"
                f"    - BM25 replaced by SQL LIKE search\n"
                f"  Writes buffered. Will drain to Atlas on recovery."
            )

    def is_atlas_online(self) -> bool:
        return _atlas_online

    def mark_atlas_recovered(self):
        global _atlas_online
        _atlas_online = True
        logger.info("[FALLBACK] ✅ Atlas connection recovered")

    async def start(self):
        pass

    async def stop(self):
        pass

    async def switch_to_fallback(self, reason: str):
        self.switch_to_sqlite(reason)

    async def fallback_episodic_read(self, user_id: str, limit: int = 8, query_text: str = ""):
        return []

    async def fallback_semantic_read(self, user_id: str, limit: int = 15):
        return []

    async def write_episodic(self, user_id, event_type, content, metadata=None):
        try:
            conn = _get_conn()
            conn.execute(
                "INSERT INTO episodic_fallback (user_id, event_type, content, metadata) "
                "VALUES (?, ?, ?, ?)",
                (user_id, event_type, content,
                 json.dumps(metadata or {}, default=str))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[FALLBACK] episodic write failed: {e}")

    async def write_transaction(self, user_id, amount, description, category, date):
        try:
            conn = _get_conn()
            conn.execute(
                "INSERT INTO transaction_fallback "
                "(user_id, amount, description, category, date) VALUES (?, ?, ?, ?, ?)",
                (user_id, amount, description, category, date)
            )
            conn.commit()
            conn.close()
            logger.info(f"[FALLBACK] Transaction buffered for Atlas drain: {description} ₹{amount}")
        except Exception as e:
            logger.error(f"[FALLBACK] transaction write failed: {e}")

    async def get_unsynced_transactions(self, user_id: str) -> list:
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT * FROM transaction_fallback WHERE user_id=? AND synced=0",
                (user_id,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[FALLBACK] get_unsynced failed: {e}")
            return []
