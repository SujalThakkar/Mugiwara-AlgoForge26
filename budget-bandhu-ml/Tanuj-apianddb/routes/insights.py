"""
Financial Insights API
Aggregates analytics from categorized + anomaly data.

Author: Tanuj
Date: Jan 13, 2026
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict
import pandas as pd
from collections import defaultdict

router = APIRouter(prefix="/api/v1", tags=["insights"])


@router.post("/insights")
async def get_insights(user_id: int, transactions: List[Dict]):
    """
    Generate comprehensive financial insights.
    
    Input: Categorized transactions from /transactions/upload
    Output: Insights, trends, recommendations
    """
    try:
        if not transactions:
            raise HTTPException(status_code=400, detail="No transactions provided")
        
        # Convert to DataFrame for analysis
        df = pd.DataFrame(transactions)
        
        # 1. Category breakdown
        category_breakdown = df.groupby('category')['amount'].agg([
            'count', 'sum', 'mean'
        ]).round(2).to_dict()
        
        # 2. Top spending categories
        top_categories = df.groupby('category')['amount'].sum().sort_values(ascending=False).head(5).to_dict()
        
        # 3. Spending trends (last 7 days vs previous)
        df['date'] = pd.to_datetime(df['date'])
        recent_trend = _compute_trend(df)
        
        # 4. Anomalies summary
        anomalies = [t for t in transactions if t.get('is_anomaly')]
        anomaly_summary = {
            'count': len(anomalies),
            'total_amount': sum(t['amount'] for t in anomalies),
            'severity_breakdown': defaultdict(int)
        }
        
        # 5. Financial health score (simple formula)
        health_score = _compute_health_score(df)
        
        # 6. Actionable insights
        insights = _generate_insights(df, anomalies)
        
        return {
            'category_breakdown': category_breakdown,
            'top_spending': top_categories,
            'trends': recent_trend,
            'anomalies': anomaly_summary,
            'health_score': health_score,
            'insights': insights,
            'timestamp': pd.Timestamp.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _compute_trend(df: pd.DataFrame) -> Dict:
    """Simple 7-day trend analysis"""
    df_sorted = df.sort_values('date')
    recent_7d = df_sorted.tail(7)['amount'].sum()
    prev_7d = df_sorted.iloc[-14:-7]['amount'].sum() if len(df_sorted) >= 14 else 0
    
    return {
        'recent_7d_total': float(recent_7d),
        'previous_7d_total': float(prev_7d),
        'change_pct': ((recent_7d - prev_7d) / prev_7d * 100) if prev_7d > 0 else 0,
        'trend': 'up' if recent_7d > prev_7d else 'down'
    }


def _compute_health_score(df: pd.DataFrame) -> Dict:
    """Simple financial health score (0-1000)"""
    total_spending = df['amount'].sum()
    num_transactions = len(df)
    anomaly_rate = len([t for t in df.to_dict('records') if t.get('is_anomaly')]) / num_transactions
    
    # Formula (production: more sophisticated)
    score = 800 - (total_spending / 10000 * 100) - (anomaly_rate * 200)
    score = max(0, min(1000, score))
    
    return {
        'score': round(score, 2),
        'components': {
            'spending_efficiency': 800,
            'anomaly_penalty': anomaly_rate * 200
        }
    }


def _generate_insights(df: pd.DataFrame, anomalies: List[Dict]) -> List[str]:
    """Generate actionable insights"""
    insights = []
    
    # Spending patterns
    top_category = df.groupby('category')['amount'].sum().idxmax()
    top_amount = df[df['category'] == top_category]['amount'].sum()
    insights.append(f"You spent Rs.{top_amount:.0f} on {top_category} - your biggest category.")
    
    # Anomalies
    if anomalies:
        insights.append(f"[!] Found {len(anomalies)} unusual transactions worth Rs.{sum(t['amount'] for t in anomalies):.0f}")
    
    # Budget suggestions (simple)
    avg_daily = df['amount'].mean()
    insights.append(f"Average daily spend: Rs.{avg_daily:.0f}. Consider 50/30/20 budgeting.")
    
    return insights
