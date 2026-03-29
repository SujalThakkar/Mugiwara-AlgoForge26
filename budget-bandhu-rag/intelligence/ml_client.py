import httpx
import os
from dotenv import load_dotenv
load_dotenv()  # Ensure .env is loaded before reading ML_SERVICE_URL

ML_BASE_URL = os.environ.get("ML_SERVICE_URL", "https://unoperated-merideth-sparklike.ngrok-free.dev")

# Required to bypass ngrok's interstitial warning page
COMMON_HEADERS = {
    "ngrok-skip-browser-warning": "true",
    "Content-Type": "application/json"
}

async def analyze_csv(csv_bytes: bytes, user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/analyze",
            headers={"ngrok-skip-browser-warning": "true"},
            files={"file": ("transactions.csv", csv_bytes, "text/csv")},
            data={"user_id": user_id}
        )
        r.raise_for_status()
        return r.json()

MERCHANT_MAP = {
    "swiggy": "Swiggy Food Delivery",
    "zomato": "Zomato Order",
    "zepto": "Zepto Quick Grocery",
    "blinkit": "Blinkit Instant",
    "amazon": "Amazon Pay India",
    "flipkart": "Flipkart Internet Pvt",
    "uber": "Uber India Trip",
    "ola": "OLA CAB Booking",
    "apollo": "Apollo Pharmacy",
    "bigbasket": "BigBasket BB Order",
    "netflix": "Netflix India Subscription",
    "jio": "Jio Recharge RJILPrepaid",
    "airtel": "Airtel Broadband Bill",
    "instamart": "Swiggy Food Delivery",
    "phonepe": "PhonePe UPI Transfer",
    "paytm": "Paytm UPI Transfer",
}

def enrich_description(raw: str) -> str:
    lower = raw.lower()
    for keyword, full_name in MERCHANT_MAP.items():
        if keyword in lower:
            return full_name
    return raw  # fallback to original if unknown

async def categorize(descriptions: list[str]) -> dict:
    enriched_descs = [enrich_description(d) for d in descriptions]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/categorize",
            headers=COMMON_HEADERS,
            json={"descriptions": enriched_descs}
        )
        r.raise_for_status()
        return r.json()

async def detect_anomalies(transactions: list[dict]) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/anomalies",
            headers=COMMON_HEADERS,
            json={"transactions": transactions}
        )
        r.raise_for_status()
        return r.json()

async def get_forecast(user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/forecast",
            headers=COMMON_HEADERS,
            json={"user_id": user_id}
        )
        r.raise_for_status()
        return r.json()

async def analyze_data(user_id: str, transactions: list[dict]) -> dict:
    """Analyze transaction data for categories, anomalies, income est, and forecast."""
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/analyze",
            headers=COMMON_HEADERS,
            json={"user_id": user_id, "transactions": transactions}
        )
        r.raise_for_status()
        return r.json()

from collections import defaultdict

def build_daily_history(transactions: list[dict]):
    daily = defaultdict(lambda: defaultdict(float))
    for t in transactions:
        if t.get("type", "debit").lower() == "debit" or t.get("transaction_type", "").lower() == "debit":
            date = str(t.get("date", t.get("created_at", "")))[:10]
            cat  = t.get("category", "Other")
            daily[date][cat] += float(t.get("amount", 0))
    return [
        {"date": d, "category_amounts": dict(cats)}
        for d, cats in sorted(daily.items())
    ]

async def forecast_from_transactions(user_id: str, transactions: list[dict], income: float = 50000) -> dict:
    """Call ML service /ml/forecast-from-transactions with raw transaction list."""
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/forecast-from-transactions",
            headers=COMMON_HEADERS,
            json={
                "user_id": user_id,
                "transactions": transactions,
                "income": income,
            }
        )
        r.raise_for_status()
        forecast_raw = r.json()

        # Normalise keys for the dashboard consumer
        forecast_7d = forecast_raw.get("forecast_7d") or forecast_raw.get("forecast_by_day") or []
        predicted_spending = (
            forecast_raw.get("predicted_spending") or
            forecast_raw.get("total_predicted_7d") or
            forecast_raw.get("total_predicted_30d") or 0
        )
        forecast = {
            "predicted_spending":  predicted_spending,
            "predicted_savings":   forecast_raw.get("predicted_savings", 0),
            "confidence":          forecast_raw.get("confidence", 0),
            "forecast_7d":         forecast_7d,
            "monthly_summary":     forecast_raw.get("monthly_summary", {
                "projected_total": forecast_raw.get("total_predicted_30d", 0),
                "top_category":    "Other"
            }),
            "processing_ms":       forecast_raw.get("processing_ms", 0),
        }
        return forecast


async def goal_eta(goal: dict, transactions: list[dict]) -> dict:
    """Call ML service to estimate goal ETA from transaction history."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/goal-eta",
            headers=COMMON_HEADERS,
            json={"goal": goal, "transactions": transactions}
        )
        r.raise_for_status()
        return r.json()

class MLClient:
    """Wrapper used by AgentController to interact with the external ML service."""
    
    def __init__(self):
        self.base_url = ML_BASE_URL
        self.headers = COMMON_HEADERS

    async def post(self, endpoint: str, json_data: dict, timeout: int = 30) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{self.base_url}{endpoint}",
                headers=self.headers,
                json=json_data
            )
            r.raise_for_status()
            return r.json()

    async def analyze_csv(self, csv_bytes: bytes, user_id: str) -> dict:
        """Call full 4-model pipeline on raw CSV bytes."""
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{self.base_url}/ml/analyze",
                headers={"ngrok-skip-browser-warning": "true"},
                files={"file": ("transactions.csv", csv_bytes, "text/csv")},
                data={"user_id": user_id}
            )
            r.raise_for_status()
            return r.json()

    async def analyze_data(self, user_id: str, transactions: list[dict]) -> dict:
        """Analyze transaction data for categories, anomalies, income est, and forecast."""
        return await self.post("/ml/analyze", {"user_id": user_id, "transactions": transactions}, timeout=45)

    async def categorize(self, descriptions: list[str]) -> dict:
        """Bulk categorization of descriptions."""
        enriched_descs = [enrich_description(d) for d in descriptions]
        return await self.post("/ml/categorize", {"descriptions": enriched_descs})

    async def detect_anomalies(self, transactions: list[dict]) -> dict:
        """Bulk anomaly detection."""
        return await self.post("/ml/anomalies", {"transactions": transactions})

    async def get_forecast(self, user_id: str) -> dict:
        """Fetch forecast for user."""
        return await self.post("/ml/forecast", {"user_id": user_id})

# For backward compatibility with existing imports
async def analyze_csv(csv_bytes: bytes, user_id: str) -> dict:
    return await MLClient().analyze_csv(csv_bytes, user_id)

async def analyze_data(user_id: str, transactions: list[dict]) -> dict:
    return await MLClient().analyze_data(user_id, transactions)

async def categorize(descriptions: list[str]) -> dict:
    return await MLClient().categorize(descriptions)

async def detect_anomalies(transactions: list[dict]) -> dict:
    return await MLClient().detect_anomalies(transactions)


