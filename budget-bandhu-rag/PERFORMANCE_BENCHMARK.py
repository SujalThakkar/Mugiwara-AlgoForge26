"""
PERFORMANCE_BENCHMARK.py — Latency measurement script for BudgetBandhu Cognitive OS.

Measures end-to-end pipeline latency for 5 representative queries.
Reports per-component timing breakdown.

Run:
    python PERFORMANCE_BENCHMARK.py

Author: Aryan Lomte
Version: 3.0.0
"""
import asyncio
import statistics
import time
from datetime import datetime, timedelta
from typing import List

from database.connection import init_db
from models.schemas import (
    AnomalyAlert, BehavioralArchetype, FinancialSnapshot,
    QueryIntent, SimulationResult, Transaction,
)
from pipeline.budget_bandhu_pipeline import BudgetBandhuPipeline


# ─────────────────────────────────────────────────────────────────────────────
# BENCHMARK QUERIES
# ─────────────────────────────────────────────────────────────────────────────

BENCHMARK_QUERIES = [
    ("SIMPLE_LOOKUP",  "How much did I spend on food last month?"),
    ("TREND_ANALYSIS", "Is my food spending increasing compared to last month?"),
    ("GOAL_PLANNING",  "How many months until I reach my emergency fund goal?"),
    ("SCENARIO_SIM",   "What if I cut dining expenses by 20 percent?"),
    ("FULL_ADVISORY",  "Give me a complete review of my financial health"),
]

TEST_USER_ID   = "benchmark_user_001"
TEST_SESSION   = "benchmark_session_001"
TEST_DB_PATH   = "benchmark_test.db"


def make_snapshot() -> FinancialSnapshot:
    """Create a realistic test financial snapshot."""
    txns: List[Transaction] = []
    base_date = datetime.utcnow() - timedelta(days=30)

    categories = [
        ("food", 800), ("food", 1200), ("food", 950),
        ("groceries", 3500), ("groceries", 2800),
        ("transport", 1500), ("transport", 1800),
        ("rent", 12000),
        ("entertainment", 2000), ("entertainment", 500),
        ("utilities", 1200),
    ]
    for i, (cat, amt) in enumerate(categories):
        txns.append(Transaction(
            id           = f"txn_{i:03d}",
            user_id      = TEST_USER_ID,
            amount       = float(amt),
            description  = f"{cat.title()} payment",
            category     = cat,
            is_credit    = False,
            date         = base_date + timedelta(days=i * 2),
        ))

    return FinancialSnapshot(
        user_id          = TEST_USER_ID,
        monthly_income   = 50000.0,
        monthly_expenses = {
            "food": 8000, "groceries": 6000, "transport": 3000,
            "rent": 12000, "entertainment": 2500, "utilities": 1500,
        },
        current_savings  = 15000.0,
        transactions     = txns,
        active_goals     = [
            {"name": "Emergency Fund", "target_amount": 150000, "current_amount": 15000},
        ],
    )


async def run_benchmark() -> None:
    """Run all benchmark queries and report timing."""
    print("\n" + "=" * 65)
    print("  BudgetBandhu Financial Cognitive OS — Performance Benchmark")
    print("=" * 65)

    # Initialise DB and pipeline
    pool     = await init_db(TEST_DB_PATH)
    pipeline = BudgetBandhuPipeline(pool, embedding_fn=None)
    snapshot = make_snapshot()

    # Warm-up run (not measured)
    print("\n[WARM-UP] Running warm-up query...")
    await pipeline.run(TEST_USER_ID, TEST_SESSION, "hello", snapshot)
    print("[WARM-UP] Done.\n")

    # Benchmark runs
    results: dict[str, list[float]] = {}

    for intent_label, query in BENCHMARK_QUERIES:
        times: list[float] = []
        print(f"[{intent_label}] '{query[:55]}...'")
        for run_n in range(3):
            t0    = time.time()
            state = await pipeline.run(TEST_USER_ID, TEST_SESSION, query, snapshot)
            ms    = (time.time() - t0) * 1000
            times.append(ms)
            tag   = "✅" if not state.error else "❌"
            print(f"  Run {run_n + 1}: {ms:.0f}ms  {tag}")

        results[intent_label] = times
        avg = statistics.mean(times)
        p95 = sorted(times)[min(2, len(times) - 1)]
        print(f"  → avg={avg:.0f}ms  p95={p95:.0f}ms\n")

    # Summary
    print("=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    all_times: list[float] = []
    for label, times in results.items():
        avg = statistics.mean(times)
        all_times.extend(times)
        status = "✅ PASS" if avg < 5000 else "⚠️  SLOW"
        print(f"  {label:<20} avg={avg:>6.0f}ms   {status}")

    overall_avg = statistics.mean(all_times)
    overall_p95 = sorted(all_times)[int(len(all_times) * 0.95)]
    print("-" * 65)
    print(f"  OVERALL avg={overall_avg:.0f}ms   p95={overall_p95:.0f}ms")
    print("=" * 65 + "\n")

    await pool.close()

    import os
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
