"""
tools/monte_carlo.py — Vectorised NumPy Monte Carlo goal simulation.

Runs 1000 independent savings trajectories in <50ms on modest hardware.
Uses vectorised operations — no Python loops over trajectories.

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from models.schemas import MonteCarloResult


def run_monte_carlo(
    current_savings: float,
    monthly_contribution: float,
    monthly_contribution_std: float,
    goal_amount: float,
    n_simulations: int = 1000,
    max_months: int = 120,
) -> MonteCarloResult:
    """
    Vectorised Monte Carlo simulation over `n_simulations` trajectories.

    Each trajectory samples monthly contributions from:
        N(monthly_contribution, monthly_contribution_std)
    clamped to ≥ 0 (can't contribute negative).

    Args:
        current_savings: Already-saved amount in ₹.
        monthly_contribution: Expected monthly savings in ₹.
        monthly_contribution_std: Standard deviation of monthly savings.
        goal_amount: Target amount in ₹.
        n_simulations: Number of Monte Carlo paths (default 1000).
        max_months: Maximum months to simulate (default 120 = 10 years).

    Returns:
        MonteCarloResult with p50, p75, p90 months and probability estimates.

    Example:
        >>> result = run_monte_carlo(20000, 5000, 1500, 100000)
        >>> result.p50_months
        16.0
        >>> result.probability_in_12m > 0.3
        True
    """
    start = time.time()

    if monthly_contribution <= 0:
        return MonteCarloResult(
            goal_amount              = goal_amount,
            current_savings          = current_savings,
            monthly_contribution     = monthly_contribution,
            p50_months               = float("inf"),
            p75_months               = float("inf"),
            p90_months               = float("inf"),
            probability_in_12m       = 0.0,
            probability_in_24m       = 0.0,
            suggested_contribution_90pct = goal_amount / 24,
            simulation_paths         = n_simulations,
        )

    remaining = max(0.0, goal_amount - current_savings)

    # Shape: (n_simulations, max_months) — all trajectories at once
    # Each cell = random monthly contribution for that simulation × month
    rng          = np.random.default_rng()
    contributions = rng.normal(
        loc   = monthly_contribution,
        scale = max(monthly_contribution_std, 1e-9),
        size  = (n_simulations, max_months),
    )
    contributions = np.maximum(contributions, 0.0)   # clamp negatives to 0

    # Cumulative sum along months axis → cumulative saved per path
    cumulative = np.cumsum(contributions, axis=1)     # shape: (n_sims, max_months)

    # For each simulation, find the first month where cumulative ≥ remaining
    # reached[i, j] = True if path i has reached goal by month j
    reached = cumulative >= remaining                  # bool (n_sims, max_months)

    # months_to_goal[i] = index of first True + 1 (months are 1-indexed)
    # If never reached, set to max_months
    months_to_goal = np.where(reached.any(axis=1),
                               reached.argmax(axis=1) + 1,
                               max_months)

    p50  = float(np.percentile(months_to_goal, 50))
    p75  = float(np.percentile(months_to_goal, 75))
    p90  = float(np.percentile(months_to_goal, 90))

    prob_12m = float(np.mean(months_to_goal <= 12))
    prob_24m = float(np.mean(months_to_goal <= 24))

    # Contribution needed for 90% confidence in < 24 months
    if prob_24m >= 0.90:
        suggested_90 = monthly_contribution
    else:
        # Binary search for minimum contribution achieving 90% in 24m
        suggested_90 = _find_contribution_for_confidence(
            current_savings, monthly_contribution_std,
            remaining, target_months=24, target_prob=0.90, rng=rng
        )

    elapsed_ms = (time.time() - start) * 1000

    return MonteCarloResult(
        goal_amount                  = goal_amount,
        current_savings              = current_savings,
        monthly_contribution         = monthly_contribution,
        p50_months                   = round(p50, 1),
        p75_months                   = round(p75, 1),
        p90_months                   = round(p90, 1),
        probability_in_12m           = round(prob_12m, 3),
        probability_in_24m           = round(prob_24m, 3),
        suggested_contribution_90pct = round(suggested_90, 2),
        simulation_paths             = n_simulations,
        computation_ms               = round(elapsed_ms, 2),
    )


def _find_contribution_for_confidence(
    current_savings: float,
    std: float,
    remaining: float,
    target_months: int,
    target_prob: float,
    rng: np.random.Generator,
    max_iters: int = 20,
) -> float:
    """
    Binary search for minimum monthly contribution achieving target_prob
    within target_months. Vectorised inner simulation.
    """
    lo, hi = 0.0, remaining  # absolute bounds

    for _ in range(max_iters):
        mid = (lo + hi) / 2
        if mid <= 0:
            hi = remaining / 2
            continue

        contribs   = rng.normal(mid, max(std, 1e-9), size=(500, target_months))
        contribs   = np.maximum(contribs, 0.0)
        cumulative = np.cumsum(contribs, axis=1)
        prob       = float(np.mean(cumulative[:, -1] >= remaining))

        if prob >= target_prob:
            hi = mid
        else:
            lo = mid

        if (hi - lo) < 10:  # ₹10 precision
            break

    return hi
