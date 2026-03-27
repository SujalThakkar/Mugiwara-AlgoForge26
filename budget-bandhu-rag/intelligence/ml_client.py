import httpx
import os

ML_BASE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")

async def analyze_csv(csv_bytes: bytes, user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/analyze",
            files={"file": ("transactions.csv", csv_bytes, "text/csv")},
            data={"user_id": user_id}
        )
        r.raise_for_status()
        return r.json()

async def categorize(descriptions: list[str]) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/categorize",
            json={"descriptions": descriptions}
        )
        r.raise_for_status()
        return r.json()

async def detect_anomalies(transactions: list[dict]) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/anomalies",
            json={"transactions": transactions}
        )
        r.raise_for_status()
        return r.json()

async def get_forecast(user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ML_BASE_URL}/ml/forecast",
            json={"user_id": user_id}
        )
        r.raise_for_status()
        return r.json()
