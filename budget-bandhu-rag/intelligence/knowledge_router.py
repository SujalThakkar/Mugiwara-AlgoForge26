"""
intelligence/knowledge_router.py — Routes query to relevant KB document IDs.
Updated for v3 knowledge base with 9 document types.
"""

_ROUTING_TABLE = {
    # Tax keywords → tax_slabs_v3
    "tax_slabs_v3": [
        "tax", "slab", "income tax", "itr", "tds", "gst", "80c", "80d",
        "80e", "80g", "tta", "ttb", "87a", "deduction", "rebate",
        "advance tax", "surcharge", "cess", "itr-1", "itr-2", "return",
        "filing", "refund", "section", "194", "271", "276", "278",
        "capital gains", "ltcg", "stcg", "exempt", "new regime", "old regime"
    ],
    # Investment keywords → investment_products_v3
    "investment_products_v3": [
        "invest", "ppf", "elss", "nps", "mutual fund", "sip", "fd",
        "fixed deposit", "recurring deposit", "rd", "stocks", "equity",
        "gold", "sgb", "sovereign bond", "real estate", "reit", "nsc",
        "sukanya", "epf", "provident fund", "crypto", "bitcoin", "vda",
        "portfolio", "returns", "compounding", "zerodha", "groww",
        "nifty", "sensex", "index fund", "debt fund", "liquid fund"
    ],
    # Banking keywords → banking_finance_v3
    "banking_finance_v3": [
        "bank", "savings account", "rbi", "repo rate", "interest rate",
        "credit score", "cibil", "upi", "neft", "rtgs", "imps", "loan",
        "home loan", "personal loan", "car loan", "emi", "credit card",
        "fd rate", "insurance", "premium", "claim", "fd", "account"
    ],
    # Government schemes → government_schemes_v3
    "government_schemes_v3": [
        "government scheme", "jan dhan", "atal pension", "mudra", "epfo",
        "pm kisan", "ayushman", "pmjay", "startup india", "scss",
        "pmvvy", "senior citizen scheme", "dpiit", "recognition",
        "subsidy", "welfare", "benefit", "yojana"
    ],
    # Budgeting → budgeting_india_v3
    "budgeting_india_v3": [
        "budget", "spend", "saving", "expense", "salary", "income",
        "50-30-20", "emergency fund", "swiggy", "zomato", "netflix",
        "ott", "subscription", "rent", "groceries", "retirement",
        "goal", "debt", "emi burden", "cost of living", "mumbai",
        "bengaluru", "delhi", "monthly", "allocation", "financial plan"
    ],
    # Insurance → insurance_india_v3
    "insurance_india_v3": [
        "insurance", "term plan", "health insurance", "vehicle", "car insurance",
        "two wheeler", "ulip", "critical illness", "claim", "premium",
        "lic", "hdfc life", "star health", "niva bupa", "cover",
        "policy", "nominee", "maturity", "surrender"
    ],
    # UPI & payments → upi_merchants_v3
    "upi_merchants_v3": [
        "upi", "phonepe", "gpay", "google pay", "paytm", "bhim",
        "payment", "transfer", "merchant", "qr code", "fraud",
        "digital wallet", "phonepay", "amazon pay", "transaction"
    ],
    # Legal sections → legal_sections_verified
    "legal_sections_verified": [
        "section", "act", "penalty", "prosecution", "legal", "law",
        "companies act", "sebi", "irdai", "rbi regulation", "compliance",
        "gst section", "income tax section", "fine", "offence"
    ],
    # Market & economy → market_economy_india
    "market_economy_india": [
        "sensex", "nifty", "market", "inflation", "cpi", "wpi",
        "sebi", "ipo", "budget 2024", "union budget", "economy",
        "interest rate", "monetary policy", "repo", "rbi policy",
        "stock market", "trading", "derivative", "f&o"
    ]
}


def route_query_to_docs(query: str) -> list[str]:
    """
    Returns list of document_ids most relevant to the query.
    Called by phi3_rag._direct_kb_fetch() for MongoDB filter.
    """
    q = query.lower()
    scores = {}
    for doc_id, keywords in _ROUTING_TABLE.items():
        score = sum(1 for kw in keywords if kw in q)
        if score > 0:
            scores[doc_id] = score

    if not scores:
        return []  # No filter → phi3_rag fetches all (limit 5)

    # Return top 3 most relevant doc IDs
    return sorted(scores, key=scores.get, reverse=True)[:3]
