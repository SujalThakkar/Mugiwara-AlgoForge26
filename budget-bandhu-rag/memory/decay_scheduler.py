"""
memory/decay_scheduler.py — Background APScheduler jobs for memory maintenance.

Runs two recurring jobs:
  - Daily decay: apply episodic decay to all active memories
  - Weekly snapshots: recompute trajectory snapshots for all active users

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class MemoryDecayScheduler:
    """
    Manages background APScheduler jobs for memory upkeep.
    Should be started once at app startup and stopped on shutdown.

    Usage:
        scheduler = MemoryDecayScheduler(
            decay_fn=episodic_store.apply_decay,
            trajectory_fn=trajectory_store.recompute_all_users,
        )
        scheduler.start()
        # ... on shutdown:
        scheduler.stop()
    """

    def __init__(
        self,
        decay_fn: Callable,
        trajectory_fn: Optional[Callable] = None,
    ):
        """
        Args:
            decay_fn: Async callable — runs daily decay on all episodic memories.
                      Signature: async def decay_fn() -> int
            trajectory_fn: Optional async callable — recomputes trajectory snapshots.
                           Signature: async def trajectory_fn() -> None
        """
        self._decay_fn      = decay_fn
        self._trajectory_fn = trajectory_fn
        self._scheduler     = AsyncIOScheduler(timezone="Asia/Kolkata")
        self._running       = False

    def start(self) -> None:
        """Register all jobs and start the scheduler."""
        # Daily at 02:00 IST — low-traffic window
        self._scheduler.add_job(
            self._run_decay,
            CronTrigger(hour=2, minute=0),
            id="episodic_decay",
            name="Episodic Memory Decay",
            replace_existing=True,
            max_instances=1,
        )

        # Weekly on Sunday at 03:00 IST
        if self._trajectory_fn:
            self._scheduler.add_job(
                self._run_trajectory,
                CronTrigger(day_of_week="sun", hour=3, minute=0),
                id="trajectory_snapshot",
                name="Trajectory Snapshot Recompute",
                replace_existing=True,
                max_instances=1,
            )

        self._scheduler.start()
        self._running = True
        logger.info("[SCHEDULER] ✅ Memory decay scheduler started")

    def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("[SCHEDULER] Memory scheduler stopped")

    async def _run_decay(self) -> None:
        try:
            count = await self._decay_fn()
            logger.info(f"[SCHEDULER] Decay job complete — {count} episodes updated")
        except Exception as e:
            logger.error(f"[SCHEDULER] Decay job failed: {e}", exc_info=True)

    async def _run_trajectory(self) -> None:
        try:
            await self._trajectory_fn()
            logger.info("[SCHEDULER] Trajectory snapshot job complete")
        except Exception as e:
            logger.error(f"[SCHEDULER] Trajectory job failed: {e}", exc_info=True)

    async def trigger_decay_now(self) -> int:
        """Manually trigger decay (useful for testing). Returns episodes updated."""
        return await self._decay_fn()

    async def trigger_trajectory_now(self) -> None:
        """Manually trigger trajectory recompute (useful for testing)."""
        if self._trajectory_fn:
            await self._trajectory_fn()
