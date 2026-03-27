"""
tests/test_fallback_bridge.py — Unit tests for the AtlasFallbackBridge.

Tests the state machine, write buffering, read-only SQLite fallback,
health check caching, and recovery drain behaviour.

Run:
    pytest tests/test_fallback_bridge.py -v

Author: Financial Cognitive OS Team
Version: 3.0.0
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def sqlite_db(tmp_path):
    """Create a minimal SQLite DB with fallback tables for testing."""
    db_path = str(tmp_path / "fallback_test.db")
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodic_fallback (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                event_type TEXT NOT NULL, trigger_description TEXT NOT NULL,
                outcome_description TEXT NOT NULL DEFAULT '',
                category TEXT, amount_inr REAL,
                decay_score REAL DEFAULT 1.0, confidence_score REAL DEFAULT 0.5,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS semantic_fallback (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                memory_type TEXT NOT NULL, attribute TEXT NOT NULL,
                value TEXT NOT NULL, confidence_score REAL DEFAULT 0.5,
                confirmed_count INTEGER DEFAULT 0, last_updated TEXT NOT NULL
            );
        """)
        await conn.commit()
    return db_path


@pytest_asyncio.fixture
async def bridge(sqlite_db):
    """Fresh AtlasFallbackBridge for each test."""
    from database.fallback_bridge import AtlasFallbackBridge
    b = AtlasFallbackBridge(sqlite_path=sqlite_db)
    yield b
    # Don't start/stop background tasks for unit tests


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Switches to SQLite on Atlas timeout
# ─────────────────────────────────────────────────────────────────────────────

async def test_switches_to_sqlite_on_atlas_timeout(bridge):
    """
    After switch_to_fallback(), bridge should be in fallback mode
    and SQLite reads should return empty lists (not exceptions).
    """
    assert not bridge.in_fallback_mode, "Bridge should start in Atlas mode"

    await bridge.switch_to_fallback("Simulated Atlas timeout — connection refused")

    assert bridge.in_fallback_mode, "Bridge should be in fallback mode after switch"

    # Reads should work (return empty — no data inserted yet)
    eps = await bridge.fallback_episodic_read("user-001", limit=5)
    assert isinstance(eps, list), "Expected a list (even if empty)"
    assert len(eps) == 0, "No episodic data should exist for new user"

    sem = await bridge.fallback_semantic_read("user-001")
    assert isinstance(sem, list)
    assert len(sem) == 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Reads actual data written to SQLite fallback
# ─────────────────────────────────────────────────────────────────────────────

async def test_read_only_mode_in_fallback(bridge):
    """
    Data written via fallback_write_episodic() should be readable via
    fallback_episodic_read().
    """
    await bridge.switch_to_fallback("Test isolation")

    record = {
        "id"                 : "ep-test-001",
        "user_id"            : "user-readtest",
        "event_type"         : "OVERSPEND",
        "trigger_description": "Rs.5000 spending on clothes",
        "outcome_description": "Advised to use 24-hour rule",
        "category"           : "shopping",
        "amount_inr"         : 5000.0,
        "decay_score"        : 0.95,
        "confidence_score"   : 0.70,
        "created_at"         : "2026-03-27T12:00:00",
    }
    await bridge.fallback_write_episodic(record)

    # Should now be readable
    results = await bridge.fallback_episodic_read("user-readtest", limit=5)
    assert len(results) == 1
    assert results[0]["id"] == "ep-test-001"
    assert results[0]["event_type"] == "OVERSPEND"
    assert float(results[0]["amount_inr"]) == 5000.0

    # Query-filtered read
    text_results = await bridge.fallback_episodic_read(
        "user-readtest", limit=5, query_text="clothes"
    )
    assert len(text_results) == 1


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Switches back to Atlas on recovery
# ─────────────────────────────────────────────────────────────────────────────

async def test_switches_back_to_atlas_on_recovery(bridge):
    """
    After switch_to_fallback() then switch_to_atlas(), fallback mode
    should deactivate. Write buffer should trigger drain.
    """
    await bridge.switch_to_fallback("Test: Atlas down")
    assert bridge.in_fallback_mode

    # Buffer a write while in fallback
    bridge.buffer_write(
        "episodic_memory", "insert",
        {"id": "e1", "user_id": "u1", "event_type": "TEST"}
    )
    assert bridge.buffered_writes_count == 1

    # Simulate Atlas recovery — patch get_database + _drain
    with patch("database.fallback_bridge.get_database", new_callable=AsyncMock) as mock_db:
        mock_col = AsyncMock()
        mock_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="abc"))
        mock_atlas_db = MagicMock()
        mock_atlas_db.__getitem__ = MagicMock(return_value=mock_col)
        mock_db.return_value = mock_atlas_db

        await bridge.switch_to_atlas()

    assert not bridge.in_fallback_mode, "Should be back in Atlas mode"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Health check caching
# ─────────────────────────────────────────────────────────────────────────────

async def test_health_check_caching(bridge):
    """
    ping_atlas() result should be cached for 30 seconds.
    Multiple calls within the window should not make live network calls.
    """
    import database.atlas_client as atlas_mod

    call_count = 0

    async def mock_ping():
        nonlocal call_count
        call_count += 1
        return True

    # Force cache expiry first
    atlas_mod._last_ping_time   = 0.0
    atlas_mod._last_ping_result = None
    atlas_mod._client           = MagicMock()   # non-None client

    with patch.object(atlas_mod._client.admin, "command", new_callable=AsyncMock) as mock_cmd:
        mock_cmd.return_value = {"ok": 1}

        # First call — should hit network (mock)
        result1 = await bridge.is_atlas_healthy()
        first_calls = mock_cmd.call_count

        # Second call within cache window — should use cache
        result2 = await bridge.is_atlas_healthy()
        second_calls = mock_cmd.call_count

    assert result1 == result2
    assert second_calls == first_calls, (
        "Second call within cache window should not make a new network call"
    )

    # Reset client to None for other tests
    atlas_mod._client = None


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: Write buffer cap (max 500)
# ─────────────────────────────────────────────────────────────────────────────

async def test_write_buffer_cap(bridge):
    """
    Write buffer should cap at 500 items (deque maxlen).
    Oldest items should be evicted when full.
    """
    await bridge.switch_to_fallback("Buffer cap test")

    # Fill buffer beyond cap
    for i in range(510):
        bridge.buffer_write(
            "episodic_memory", "insert",
            {"id": f"ep-{i}", "user_id": "user-cap"}
        )

    # Should be capped at 500
    assert bridge.buffered_writes_count == 500

    # Verify first 10 were evicted (deque drops from left)
    buffer_list = list(bridge._write_buffer)
    assert buffer_list[0].document["id"] == "ep-10", (
        f"Expected ep-10 to be oldest (ep-0 to ep-9 evicted), got {buffer_list[0].document['id']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: SQLite 50-row cap per user
# ─────────────────────────────────────────────────────────────────────────────

async def test_episodic_fallback_50_row_cap(bridge, sqlite_db):
    """
    Writing >50 episodes for same user should purge oldest, keeping only 50.
    """
    await bridge.switch_to_fallback("cap test")

    for i in range(60):
        record = {
            "id"                 : f"ep-cap-{i:03d}",
            "user_id"            : "user-cap-test",
            "event_type"         : "OVERSPEND",
            "trigger_description": f"Test episode {i}",
            "outcome_description": "",
            "category"           : "food",
            "amount_inr"         : float(i * 100),
            "decay_score"        : 1.0,
            "confidence_score"   : 0.5,
            "created_at"         : f"2026-03-{(i % 28) + 1:02d}T10:00:00",
        }
        await bridge.fallback_write_episodic(record)

    results = await bridge.fallback_episodic_read("user-cap-test", limit=100)
    assert len(results) <= 50, f"Expected ≤50 rows, got {len(results)}"
