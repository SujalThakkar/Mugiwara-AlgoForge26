#!/usr/bin/env python3
"""
scripts/update_ngrok_urls.py
Fetches active ngrok tunnels, updates budget-bandhu-rag/.env with ML_SERVICE_URL,
and prints Vercel environment variables for easy copy-pasting.

Run this script after starting ngrok:
    ngrok start --all
"""
import os
import sys
import time

RAG_URL_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ngrok_url.txt")
ML_URL_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "budget-bandhu-models", "ngrok_url.txt")
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

def read_url(filepath, timeout=5):
    for _ in range(timeout):
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                content = f.read().strip()
                if "Public URL: " in content:
                    return content.split("Public URL: ")[1].strip()
        time.sleep(1)
    return None

def update_env_file(ml_url):
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            lines = f.readlines()
            
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith("ML_SERVICE_URL="):
            new_lines.append(f"ML_SERVICE_URL={ml_url}\n")
            updated = True
        else:
            new_lines.append(line)
            
    if not updated:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"ML_SERVICE_URL={ml_url}\n")
        
    with open(ENV_FILE, "w") as f:
        f.writelines(new_lines)
    print(f"✅ Updated {ENV_FILE} with ML_SERVICE_URL={ml_url}")

def main():
    print("⏳ Scanning for active ngrok tunnels across both backends...")
    rag_url = read_url(RAG_URL_FILE)
    ml_url = read_url(ML_URL_FILE)
    
    if not rag_url or not ml_url:
        print("❌ Error: Could not find ngrok URLs for both backends!")
        print(f"   RAG found: {rag_url}")
        print(f"   ML found: {ml_url}")
        print("💡 Make sure both `python -m uvicorn api.main:app` processes are running successfully.")
        sys.exit(1)

    # 1. Update backend .env for inter-service communication
    update_env_file(ml_url)
    
    # 2. Derive WebSocket URL 
    ws_url = rag_url.replace("https://", "wss://").replace("http://", "ws://")
    
    # 3. Print Vercel variables
    print("\n" + "="*60)
    print("🚀 VERCEL ENVIRONMENT VARIABLES (Frontend Dashboard)")
    print("="*60)
    print(f"NEXT_PUBLIC_RAG_URL={rag_url}")
    print(f"NEXT_PUBLIC_ML_URL={ml_url}")
    print(f"NEXT_PUBLIC_RAG_WS_URL={ws_url}")
    print("="*60)
    print("\nCopy & paste these directly into your Next.js project settings.")

if __name__ == "__main__":
    main()
