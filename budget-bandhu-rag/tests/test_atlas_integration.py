"""
tests/test_atlas_integration.py — Integration tests for Atlas-backed memory system.

Uses mongomock-motor for in-memory MongoDB simulation (no real Atlas connection needed).

Run:
    pip install mongomock-motor pytest pytest-asyncio
    pytest tests/test_atlas_integration.py -v

Author: Financial Cognitive OS Team
Version: 3.0.0
"""
from __future__ import annotations

import asyncio
import pickle
from datetime import datetime
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

try:
    from mongomock_motor import AsyncMongoMockClient
    MONGOMOCK_AVAILABLE = True
except ImportError:
    MONGOMOCK_AVAILABLE = False

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def mock_db():
    """In-memory MongoDB using mongomock_motor."""
    if not MONGOMOCK_AVAILABLE:
        pytest.skip("mongomock-motor not installed — run: pip install mongomock-motor")
    client = AsyncMongoMockClient()
    db     = client["budget_bandhu_test"]
    yield db
    client.close()


@pytest_asyncio.fixture
def simple_embedding_fn():
    """Dummy 384-dim embedding function for testing."""
    import numpy as np
    def _embed(text: str):
        rng = np.random.RandomState(abs(hash(text)) % (2**31))
        vec = rng.randn(384).astype("float32")
        vec /= (vec ** 2).sum() ** 0.5   # normalise
        return vec
    return _embed


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Episodic store and retrieve
# ─────────────────────────────────────────────────────────────────────────────

async def test_episodic_store_and_retrieve(mock_db, simple_embedding_fn):
    """Storing an episode and retrieving it by user_id should return it."""
    from memory.episodic_memory import EpisodicMemoryStore

    store = EpisodicMemoryStore(mock_db, simple_embedding_fn)

    ep_id = await store.store_episode(
        user_id             = "user-test-1",
        event_type          = "OVERSPEND",
        trigger_description = "Spent Rs.3000 on Zomato last weekend",
        outcome_description = "Advised to set a dining cap",
        category            = "food",
        amount_inr          = 3000.0,
    )

    assert ep_id, "Expected a non-empty episode ID"

    results = await store.retrieve("user-test-1", limit=5)
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    assert results[0].event_type == "OVERSPEND"
    assert results[0].amount_inr == 3000.0
    assert results[0].category == "food"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Vector search returns ranked results
# ─────────────────────────────────────────────────────────────────────────────

async def test_vector_search_returns_ranked_results(mock_db, simple_embedding_fn):
    """
    Inserting multiple episodes then vector-searching should return results
    (mongomock doesn't support $vectorSearch, so we test the fallback retrieve path).
    """
    from memory.episodic_memory import EpisodicMemoryStore

    store = EpisodicMemoryStore(mock_db, simple_embedding_fn)

    descriptions = [
        ("OVERSPEND", "Dining at expensive restaurant"),
        ("SAVINGS",   "Transferred Rs.5000 to savings account"),
        ("OVERSPEND", "Ordered food delivery three times"),
        ("ANOMALY",   "Unusually large grocery bill"),
    ]
    for event_type, trigger in descriptions:
        await store.store_episode("user-vec-1", event_type, trigger, "advice given")

    # Falls back to simple retrieve when $vectorSearch unsupported (mongomock)
    import numpy as np
    q_emb = simple_embedding_fn("food spending this week").tolist()

    # Direct retrieve should return all 4 stored items
    results = await store.retrieve("user-vec-1", limit=10)
    assert len(results) == 4, f"Expected 4 stored episodes, got {len(results)}"

    # All belong to the right user
    assert all(r.user_id == "user-vec-1" for r in results)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Knowledge graph multi-hop via $graphLookup
# ─────────────────────────────────────────────────────────────────────────────

async def test_knowledge_graph_multi_hop(mock_db):
    """
    Inserting edges and performing multi_hop_query should return path strings.
    Note: mongomock supports basic $match but not full $graphLookup —
    we verify the insert + retrieve path (direct find) instead.
    """
    from memory.knowledge_graph import KnowledgeGraphStore
    from models.schemas import EdgeRelationship

    store = KnowledgeGraphStore(mock_db)

    # Insert edges
    await store.upsert_edge("user-kg-1", "user",  EdgeRelationship.OVERSPENDS_ON,  "food",    "entity",   "category", 2.0)
    await store.upsert_edge("user-kg-1", "food",  EdgeRelationship.COMPETES_WITH,  "savings", "category", "goal",     1.0)
    await store.upsert_edge("user-kg-1", "user",  EdgeRelationship.TARGETS,        "savings", "entity",   "goal",     1.5)

    # Verify spending patterns (direct find, no $graphLookup needed)
    patterns = await store.get_spending_patterns("user-kg-1")
    assert len(patterns) >= 1, "Expected at least one OVERSPENDS_ON edge"
    assert patterns[0].target_node == "food"
    assert patterns[0].weight >= 2.0

    # Competing goals
    competing = await store.get_competing_goals("user-kg-1", "food")
    assert len(competing) >= 1, "Expected food to compete with savings"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Procedural strategy EMA update
# ─────────────────────────────────────────────────────────────────────────────

async def test_procedural_strategy_ema_update(mock_db):
    """Success/failure updates should shift success_rate via EMA formula."""
    from memory.procedural_memory import ProceduralMemoryStore, _EMA_ALPHA

    store = ProceduralMemoryStore(mock_db)
    n = await store.seed_default_strategies("user-proc-1")
    assert n == 6, f"Expected 6 strategies seeded, got {n}"

    # Fetch the soft_nudge strategy
    strategy = await store.get_best_strategy("user-proc-1", "OVERSPEND", "impulse_spender_reward_driven")
    assert strategy is not None, "Expected a matching strategy"
    assert strategy.strategy_id == "soft_nudge_positive_frame"

    initial_rate = strategy.success_rate   # 0.5 default

    # Apply multiple successes
    for _ in range(3):
        await store.update_outcome(strategy.strategy_id, "user-proc-1", success=True)

    updated = await store.get_best_strategy("user-proc-1", "OVERSPEND", "impulse_spender_reward_driven")
    assert updated is not None
    # EMA: 0.3*1.0 + 0.7*prev — after 3 successes rate should increase
    assert updated.success_rate > initial_rate, (
        f"Expected success_rate to increase from {initial_rate}, got {updated.success_rate}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: Trajectory archetype classification
# ─────────────────────────────────────────────────────────────────────────────

async def test_trajectory_archetype_classification(mock_db):
    """classify_archetype() should return correct archetype for given metrics."""
    from memory.trajectory_memory import classify_archetype
    from models.schemas import BehavioralArchetype

    # Impulse spender — high weekend ratio
    arch = classify_archetype(
        weekday_weekend_ratio=2.5, savings_rate=0.05,
        goal_adherence=0.3, anomaly_frequency=1, income_stability=0.8
    )
    assert arch == BehavioralArchetype.IMPULSE_SPENDER

    # Disciplined saver
    arch = classify_archetype(
        weekday_weekend_ratio=0.8, savings_rate=0.25,
        goal_adherence=0.80, anomaly_frequency=0, income_stability=0.9
    )
    assert arch == BehavioralArchetype.DISCIPLINED_SAVER

    # Volatile spender
    arch = classify_archetype(
        weekday_weekend_ratio=1.1, savings_rate=0.08,
        goal_adherence=0.4, anomaly_frequency=7, income_stability=0.7
    )
    assert arch == BehavioralArchetype.VOLATILE_SPENDER

    # Income anxious
    arch = classify_archetype(
        weekday_weekend_ratio=1.0, savings_rate=0.10,
        goal_adherence=0.5, anomaly_frequency=2, income_stability=0.40
    )
    assert arch == BehavioralArchetype.INCOME_ANXIOUS

    # Balance optimizer fallback
    arch = classify_archetype(
        weekday_weekend_ratio=1.0, savings_rate=0.12,
        goal_adherence=0.55, anomaly_frequency=1, income_stability=0.75
    )
    assert arch == BehavioralArchetype.UNKNOWN  # "balanced_optimizer" maps to UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: Fallback bridge on Atlas timeout (mocked)
# ─────────────────────────────────────────────────────────────────────────────

async def test_fallback_bridge_on_atlas_timeout(tmp_path):
    """
    When Atlas is unreachable, AtlasFallbackBridge should:
    - Switch to fallback mode
    - Return SQLite reads (empty for new DB)
    - Buffer writes for later drain
    """
    from database.fallback_bridge import AtlasFallbackBridge

    sqlite_path = str(tmp_path / "test_fallback.db")

    # Create the fallback tables first
    import aiosqlite
    async with aiosqlite.connect(sqlite_path) as conn:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodic_fallback (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                event_type TEXT NOT NULL, trigger_description TEXT NOT NULL,
                outcome_description TEXT NOT NULL DEFAULT '',
                category TEXT, amount_inr REAL, decay_score REAL DEFAULT 1.0,
                confidence_score REAL DEFAULT 0.5, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS semantic_fallback (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                memory_type TEXT NOT NULL, attribute TEXT NOT NULL,
                value TEXT NOT NULL, confidence_score REAL DEFAULT 0.5,
                confirmed_count INTEGER DEFAULT 0, last_updated TEXT NOT NULL
            );
        """)
        await conn.commit()

    bridge = AtlasFallbackBridge(sqlite_path)
    assert not bridge.in_fallback_mode

    # Simulate Atlas failure
    await bridge.switch_to_fallback("Test: Atlas unreachable")
    assert bridge.in_fallback_mode

    # Reads should return empty (no data yet), not raise
    eps = await bridge.fallback_episodic_read("user-test", limit=10)
    assert isinstance(eps, list)

    # Buffer a write
    bridge.buffer_write("episodic_memory", "insert", {"id": "test-1", "user_id": "user-test"})
    assert bridge.buffered_writes_count == 1

    # Second switch_to_fallback is idempotent
    await bridge.switch_to_fallback("duplicate call")
    assert bridge.buffered_writes_count == 1   # still 1, not 2


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: Hybrid retriever RRF merge
# ─────────────────────────────────────────────────────────────────────────────

async def test_hybrid_retriever_rrf_merge(mock_db):
    """
    RRF merge with 3 result lists should correctly assign scores and deduplicate.
    """
    from rag.hybrid_retriever import HybridRetriever
    from models.schemas import MemoryTier, RetrievedChunk

    retriever = HybridRetriever(mock_db, embedding_fn=None)

    def make_chunk(cid: str, tier: MemoryTier, score: float) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=cid, source_tier=tier,
            content=f"content for {cid}", score=score,
        )

    # Three overlapping result lists
    list_a = [make_chunk("c1", MemoryTier.EPISODIC, 0.9),
              make_chunk("c2", MemoryTier.EPISODIC, 0.7)]
    list_b = [make_chunk("c2", MemoryTier.EPISODIC, 0.8),   # c2 appears in both
              make_chunk("c3", MemoryTier.SEMANTIC,  0.6)]
    list_c = [make_chunk("c1", MemoryTier.EPISODIC, 0.85),  # c1 appears in both a + c
              make_chunk("c4", MemoryTier.SEMANTIC,  0.5)]

    merged = retriever._rrf_merge([list_a, list_b, list_c], top_k=4)

    chunk_ids = [c.chunk_id for c in merged]
    assert len(merged) == 4, f"Expected 4 unique chunks, got {len(merged)}"
    assert "c1" in chunk_ids, "c1 appeared in 2 lists — should rank high"
    assert "c2" in chunk_ids, "c2 appeared in 2 lists"
    # c1 and c2 should rank above c3 and c4 (appear in more lists)
    top2 = set(chunk_ids[:2])
    assert top2 == {"c1", "c2"}, f"Expected c1, c2 at top, got {top2}"
