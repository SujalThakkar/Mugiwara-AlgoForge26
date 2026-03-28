#!/usr/bin/env python
# _verify_imports.py
import sys
import os

# Add the current directory to sys.path
sys.path.append(os.getcwd())

try:
    from core.agent_controller import AgentController
    print("AgentController import: OK")
except ImportError as e:
    print(f"AgentController import: FAILED - {e}")

try:
    from database.mongo_manager import MongoManager
    print("MongoManager import: OK")
except ImportError as e:
    print(f"MongoManager import: FAILED - {e}")

try:
    from database.fallback_bridge import AtlasFallbackBridge
    print("AtlasFallbackBridge import: OK")
except ImportError as e:
    print(f"AtlasFallbackBridge import: FAILED - {e}")
