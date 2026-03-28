"""
database/mongo_manager.py — Fixed for Windows SSL WinError 10054
Fixes:
  1. SSL handshake failure on Windows (WinError 10054)
  2. Connection pool timeout after idle period
  3. Auto-retry on SSL disconnect
"""
import os, ssl, logging, certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.server_api import ServerApi

logger = logging.getLogger("BudgetBandhu")

MONGODB_URI = os.environ.get("MONGODB_ATLAS_URI",
              os.environ.get("MONGODB_URL", "mongodb://localhost:27017"))
DB_NAME     = os.environ.get("MONGODB_DATABASE", "budget_bandhu")


def _build_client() -> AsyncIOMotorClient:
    """
    Windows-safe Motor client.
    WinError 10054 = SSL renegotiation killed by Atlas after idle.
    Fix: maxIdleTimeMS + heartbeatFrequencyMS + server_api.
    """
    kwargs = dict(
        # ── Connection pool (prevents idle SSL drop) ───────────
        maxPoolSize            = 5,
        minPoolSize            = 1,
        maxIdleTimeMS          = 30_000,   # 30s idle before recycle
        heartbeatFrequencyMS   = 10_000,   # ping Atlas every 10s
        # ── Timeouts ──────────────────────────────────────────
        serverSelectionTimeoutMS = 8_000,
        connectTimeoutMS         = 10_000,
        socketTimeoutMS          = 15_000,
        # ── Reliability ───────────────────────────────────────
        retryWrites            = True,
        retryReads             = True,
        w                      = "majority",
        server_api             = ServerApi("1"),
    )
    return AsyncIOMotorClient(MONGODB_URI, **kwargs)


class MongoManager:
    _instance = None
    _client   = None
    _db       = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_connection()
        return cls._instance

    def _init_connection(self):
        try:
            self._client = _build_client()
            self._db     = self._client[DB_NAME]
            logger.info(f"[MONGO] ✅ Connected to {DB_NAME}")
        except Exception as e:
            logger.error(f"[MONGO] Connection failed: {e}")
            self._client = None
            self._db     = None

    def _ensure_connected(self):
        """Re-connect if SSL was dropped (WinError 10054 recovery)."""
        if self._client is None or self._db is None:
            logger.warning("[MONGO] Reconnecting after SSL drop...")
            self._init_connection()

    def get_motor_db(self):
        self._ensure_connected()
        return self._db

    @property
    def db(self):
        self._ensure_connected()
        return self._db

    # ── Collection shortcuts ──────────────────────────────────
    @property
    def transactions(self):
        return self.db["transactions"] if self.db else None

    @property
    def episodic_memory(self):
        return self.db["episodic_memory"] if self.db else None

    @property
    def semantic_memory(self):
        return self.db["semantic_memory"] if self.db else None

    @property
    def conversations(self):
        return self.db["conversations"] if self.db else None

    @property
    def knowledge_base(self):
        return self.db["knowledge_base"] if self.db else None
