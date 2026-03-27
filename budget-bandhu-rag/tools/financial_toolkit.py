"""
tools/financial_toolkit.py — Deterministic financial math engine.

ZERO LLM ARITHMETIC. All numbers come from here.

Provides:
  - budget_calculator: 50/30/20 compliance, surplus/deficit, ranked cuts
  - goal_planner: months-to-goal and required-monthly calculations
  - scenario_engine: impact diff vs baseline
  - subscription_detector: recurring charge pattern detection
  - anomaly_detector: Z-score per category + duplicate / odd-hour detection

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import math
import re
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from models.schemas import (
    AnomalyAlert, BudgetResult, FinancialSnapshot, GoalPlan,
    ScenarioResult, SubscriptionPattern, Transaction,
)


# ─────────────────────────────────────────────────────────────────────────────
# BUDGET CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────

def budget_calculator(
    income: float,
    expenses: Dict[str, float],
    period: str = "monthly",
) -> BudgetResult:
    """
    Compute a comprehensive budget breakdown.

    50/30/20 rule:
      Needs (50%): rent, utilities, groceries, transport, emi, medical, insurance
      Wants (30%): dining, entertainment, shopping, travel, subscriptions
      Savings (20%): savings, investment

    Args:
        income: Gross income in ₹ for the period.
        expenses: {category: amount_inr} dict.
        period: 'monthly' | 'weekly' | 'annual'.

    Returns:
        BudgetResult with full breakdown.

    Example:
        >>> result = budget_calculator(50000, {"food": 8000, "rent": 12000, "savings": 5000})
        >>> result.savings_rate
        0.1
    """
    _NEEDS  = {"rent", "utilities", "groceries", "transport", "emi", "medical",
               "insurance", "electricity", "water", "internet"}
    _WANTS  = {"dining", "food", "entertainment", "shopping", "travel",
               "subscriptions", "clothing", "subscriptions", "apps"}
    _SAVINGS = {"savings", "investment", "fd", "mutual_fund", "ppf", "elss"}

    total_expenses  = sum(expenses.values())
    surplus_deficit = income - total_expenses
    savings_rate    = max(0.0, surplus_deficit / income) if income > 0 else 0.0

    # Category breakdown as % of income
    category_breakdown = {
        cat: round(amt / income * 100, 1)
        for cat, amt in expenses.items() if income > 0
    }

    # 50/30/20 allocation
    target_needs    = income * 0.50
    target_wants    = income * 0.30
    target_savings  = income * 0.20

    actual_needs    = sum(v for k, v in expenses.items() if k.lower() in _NEEDS)
    actual_wants    = sum(v for k, v in expenses.items() if k.lower() in _WANTS)
    actual_savings  = sum(v for k, v in expenses.items() if k.lower() in _SAVINGS)

    rule_5030_20 = {
        "needs_target": target_needs, "needs_actual": actual_needs,
        "wants_target": target_wants, "wants_actual": actual_wants,
        "savings_target": target_savings, "savings_actual": actual_savings,
    }
    rule_compliance = {
        "needs_ok"  : actual_needs    <= target_needs,
        "wants_ok"  : actual_wants    <= target_wants,
        "savings_ok": actual_savings  >= target_savings,
    }

    # Recommended cuts — categories over their pro-rata budget, sorted by over-spend
    pro_rata = income / max(len(expenses), 1)
    cuts: List[Tuple[str, float]] = []
    for cat, amt in expenses.items():
        if cat.lower() in _SAVINGS:
            continue
        overspend = amt - (income * 0.05)  # each category ideally ≤ 5% of income
        if overspend > 0:
            cuts.append((cat, round(overspend, 2)))
    cuts.sort(key=lambda x: x[1], reverse=True)

    return BudgetResult(
        income            = income,
        total_expenses    = total_expenses,
        savings_rate      = round(savings_rate, 4),
        surplus_deficit   = round(surplus_deficit, 2),
        category_breakdown= category_breakdown,
        rule_50_30_20     = rule_5030_20,
        rule_compliance   = rule_compliance,
        recommended_cuts  = cuts[:5],
        period            = period,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GOAL PLANNER
# ─────────────────────────────────────────────────────────────────────────────

def goal_planner(
    goal_amount: float,
    current_savings: float,
    monthly_surplus: float,
    target_date: Optional[date] = None,
) -> GoalPlan:
    """
    Solve for months-to-goal OR required monthly surplus for a target date.

    Compound (no interest assumed for simplicity; add interest_rate param later).

    Args:
        goal_amount: Target amount in ₹.
        current_savings: Already saved in ₹.
        monthly_surplus: Money available each month in ₹.
        target_date: If provided, compute required_monthly_for_target_date.

    Returns:
        GoalPlan with milestone schedule.

    Example:
        >>> plan = goal_planner(100000, 20000, 5000)
        >>> plan.months_to_goal
        16.0
    """
    remaining = max(0.0, goal_amount - current_savings)

    if monthly_surplus <= 0:
        months_to_goal = float("inf")
        recommended = f"Current surplus is ₹{monthly_surplus:,.0f}. Increase monthly savings to make progress."
    else:
        months_to_goal = math.ceil(remaining / monthly_surplus)
        recommended = f"Save ₹{monthly_surplus:,.0f} per month consistently."

    required_monthly: Optional[float] = None
    shortfall: Optional[float] = None

    if target_date:
        days_remaining = max(0, (target_date - date.today()).days)
        months_remaining = max(1, days_remaining / 30.44)
        required_monthly = remaining / months_remaining
        shortfall = max(0.0, required_monthly - monthly_surplus)
        if shortfall > 0:
            recommended = (
                f"You need ₹{required_monthly:,.0f}/month to meet your deadline "
                f"(currently short by ₹{shortfall:,.0f}/month)."
            )

    # Milestone schedule (every 25% of remaining goal)
    milestones: List[Tuple[int, float]] = []
    step_amount = remaining / 4
    for i in range(1, 5):
        milestone_amount = current_savings + step_amount * i
        if monthly_surplus > 0:
            months_to_milestone = max(1, round(step_amount * i / monthly_surplus))
        else:
            months_to_milestone = 999
        milestones.append((months_to_milestone, round(milestone_amount, 2)))

    return GoalPlan(
        goal_amount                   = goal_amount,
        current_savings               = current_savings,
        monthly_surplus               = monthly_surplus,
        months_to_goal                = float(months_to_goal),
        required_monthly_for_target_date = round(required_monthly, 2) if required_monthly else None,
        shortfall_amount              = round(shortfall, 2) if shortfall else None,
        milestone_schedule            = milestones,
        recommended_action            = recommended,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def scenario_engine(
    baseline: FinancialSnapshot,
    scenario_changes: Dict[str, float],
) -> ScenarioResult:
    """
    Compute the financial impact of hypothetical changes vs baseline.

    Args:
        baseline: Current FinancialSnapshot.
        scenario_changes: Dict with any of:
            - income_change_pct: e.g., 20 means +20% income
            - {category}_cut_pct: e.g., food_cut_pct=15 reduces food by 15%
            - additional_savings: flat ₹ added to savings monthly

    Returns:
        ScenarioResult with savings rate diff and goal timeline delta.

    Example:
        >>> result = scenario_engine(baseline, {"food_cut_pct": 20, "income_change_pct": 10})
        >>> result.new_savings_rate
        0.28
    """
    # Compute baseline metrics
    baseline_expenses = sum(baseline.monthly_expenses.values())
    baseline_surplus  = baseline.monthly_income - baseline_expenses
    baseline_rate     = max(0.0, baseline_surplus / baseline.monthly_income) if baseline.monthly_income else 0

    # Apply scenario changes
    new_income   = baseline.monthly_income
    new_expenses = dict(baseline.monthly_expenses)

    key_changes: List[str] = []

    if "income_change_pct" in scenario_changes:
        pct = scenario_changes["income_change_pct"]
        new_income = baseline.monthly_income * (1 + pct / 100)
        direction  = "increase" if pct > 0 else "decrease"
        key_changes.append(f"Income {direction} of {abs(pct):.0f}% → ₹{new_income:,.0f}/month")

    for key, val in scenario_changes.items():
        if key.endswith("_cut_pct"):
            cat = key.replace("_cut_pct", "")
            if cat in new_expenses:
                saved = new_expenses[cat] * (val / 100)
                new_expenses[cat] = max(0.0, new_expenses[cat] - saved)
                key_changes.append(f"{cat.title()} cut by {val:.0f}% → saves ₹{saved:,.0f}/month")

    if "additional_savings" in scenario_changes:
        amt = scenario_changes["additional_savings"]
        key_changes.append(f"Additional savings of ₹{amt:,.0f}/month")
        # Treat as expense reduction (money not spent)
        new_expenses["_scenario_savings"] = new_expenses.get("_scenario_savings", 0) + amt

    new_total_expenses = sum(new_expenses.values())
    new_surplus        = new_income - new_total_expenses
    new_rate           = max(0.0, new_surplus / new_income) if new_income else 0

    # Estimate goal timeline delta (assumes 6-month emergency fund goal)
    sample_goal = baseline.monthly_income * 6
    old_months  = math.ceil(sample_goal / baseline_surplus) if baseline_surplus > 0 else 999
    new_months  = math.ceil(sample_goal / new_surplus)      if new_surplus > 0      else 999
    timeline_delta = new_months - old_months  # negative = faster

    impact_score = min(1.0, abs(new_rate - baseline_rate) / 0.2)  # normalise to 0–1

    recommended: Optional[str] = None
    if new_rate > baseline_rate + 0.05:
        recommended = "This scenario significantly improves your savings rate. Consider implementing it."
    elif new_rate < baseline_rate:
        recommended = "This scenario reduces savings. Identify which change has the most negative impact."

    return ScenarioResult(
        scenario_label        = "Scenario Analysis",
        baseline_savings_rate = round(baseline_rate, 4),
        new_savings_rate      = round(new_rate, 4),
        baseline_monthly_surplus= round(baseline_surplus, 2),
        new_monthly_surplus   = round(new_surplus, 2),
        goal_timeline_delta_months= float(timeline_delta),
        impact_score          = round(impact_score, 3),
        key_changes           = key_changes,
        recommended_action    = recommended,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ANOMALY DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

def detect_anomalies(
    transactions: List[Transaction],
    lookback_days: int = 30,
) -> List[AnomalyAlert]:
    """
    Multi-method anomaly detection — no ML model needed.

    Methods:
    1. Z-score per category (flag |z| > 2.0)
    2. Duplicate charge detection (same amount ±₹5 within 24h)
    3. Odd-hour transactions (11 PM – 4 AM)

    Args:
        transactions: List of Transaction objects.
        lookback_days: Historical window for baseline computation.

    Returns:
        List of AnomalyAlert sorted by severity.

    Example:
        >>> alerts = detect_anomalies(txns)
        >>> alerts[0].anomaly_type
        'category_spike'
    """
    cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
    recent  = [t for t in transactions if t.date >= cutoff and not t.is_credit]

    # Build per-category stats
    cat_amounts: Dict[str, List[float]] = defaultdict(list)
    for t in recent:
        cat_amounts[t.category].append(t.amount)

    alerts: List[AnomalyAlert] = []

    # Method 1: Z-score per category
    for t in recent:
        amounts = cat_amounts.get(t.category, [])
        if len(amounts) < 3:
            continue
        mean = statistics.mean(amounts)
        std  = statistics.stdev(amounts)
        if std < 1e-9:
            continue
        z = (t.amount - mean) / std
        if abs(z) > 2.0:
            severity = "HIGH" if abs(z) > 3.0 else "MEDIUM"
            alerts.append(
                AnomalyAlert(
                    transaction_id = t.id,
                    description    = t.description,
                    amount         = t.amount,
                    category       = t.category,
                    z_score        = round(z, 2),
                    anomaly_type   = "category_spike",
                    severity       = severity,
                )
            )

    # Method 2: Duplicate charge detection
    sorted_txns = sorted(recent, key=lambda x: x.date)
    for i, t1 in enumerate(sorted_txns):
        for t2 in sorted_txns[i + 1:]:
            if (t2.date - t1.date).total_seconds() > 86400:
                break
            if (
                t1.merchant == t2.merchant
                and abs(t1.amount - t2.amount) <= 5.0
                and t1.id != t2.id
            ):
                alerts.append(
                    AnomalyAlert(
                        transaction_id = t2.id,
                        description    = f"Possible duplicate of {t1.description}",
                        amount         = t2.amount,
                        category       = t2.category,
                        z_score        = 0.0,
                        anomaly_type   = "duplicate",
                        severity       = "HIGH",
                    )
                )

    # Method 3: Odd-hour transactions (11 PM – 4 AM)
    for t in recent:
        hour = t.date.hour
        if hour >= 23 or hour <= 4:
            alerts.append(
                AnomalyAlert(
                    transaction_id = t.id,
                    description    = t.description,
                    amount         = t.amount,
                    category       = t.category,
                    z_score        = 0.0,
                    anomaly_type   = "odd_hour",
                    severity       = "LOW",
                )
            )

    # Sort: HIGH → MEDIUM → LOW
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    alerts.sort(key=lambda a: (severity_order.get(a.severity, 2), -abs(a.z_score)))
    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# SUBSCRIPTION DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

def detect_subscriptions(
    transactions: List[Transaction],
    lookback_days: int = 90,
) -> List[SubscriptionPattern]:
    """
    Identify recurring charges that may be forgotten subscriptions.

    Pattern criteria:
      - Same merchant appears 2+ times
      - Amount variance < 10%
      - Interval variance < 4 days

    Args:
        transactions: Transaction history to analyse.
        lookback_days: How far back to look for recurring patterns.

    Returns:
        List of SubscriptionPattern sorted by annual_cost DESC.

    Example:
        >>> subs = detect_subscriptions(txns)
        >>> subs[0].merchant
        'Netflix'
    """
    cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
    expense = [t for t in transactions if not t.is_credit and t.date >= cutoff]

    by_merchant: Dict[str, List[Transaction]] = defaultdict(list)
    for t in expense:
        merchant = (t.merchant or t.description or "Unknown").strip()
        by_merchant[merchant].append(t)

    patterns: List[SubscriptionPattern] = []

    for merchant, txns in by_merchant.items():
        if len(txns) < 2:
            continue

        txns_sorted = sorted(txns, key=lambda x: x.date)
        amounts     = [t.amount for t in txns_sorted]
        mean_amount = statistics.mean(amounts)

        if mean_amount < 1:
            continue

        # Check amount variance < 10%
        max_var = max(abs(a - mean_amount) / mean_amount for a in amounts)
        if max_var > 0.10:
            continue

        # Check interval variance < 4 days
        intervals = [
            (txns_sorted[i + 1].date - txns_sorted[i].date).days
            for i in range(len(txns_sorted) - 1)
        ]
        if not intervals:
            continue

        mean_interval = statistics.mean(intervals)
        if mean_interval < 1:
            continue

        interval_var = max(abs(iv - mean_interval) for iv in intervals)
        if interval_var > 4:
            continue

        next_expected: Optional[date] = None
        if mean_interval > 0:
            next_dt = txns_sorted[-1].date + timedelta(days=round(mean_interval))
            next_expected = next_dt.date() if isinstance(next_dt, datetime) else next_dt

        annual_multiplier = 365 / mean_interval if mean_interval > 0 else 12
        patterns.append(
            SubscriptionPattern(
                merchant             = merchant,
                monthly_cost         = round(mean_amount * (30 / mean_interval), 2),
                annual_cost          = round(mean_amount * annual_multiplier, 2),
                last_charged         = txns_sorted[-1].date,
                next_expected        = next_expected,
                transaction_count    = len(txns),
                amount_variance_pct  = round(max_var * 100, 1),
                interval_days        = round(mean_interval, 1),
            )
        )

    patterns.sort(key=lambda p: p.annual_cost, reverse=True)
    return patterns
