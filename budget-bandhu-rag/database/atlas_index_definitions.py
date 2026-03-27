"""
database/atlas_index_definitions.py — Atlas Search and Vector Search index definitions.

IMPORTANT — Atlas Search and Vector Search indexes CANNOT be created via Motor/PyMongo.
They must be created via:
  Option A: Atlas UI (Database → Search Indexes → Create Index)
  Option B: mongocli / Atlas CLI:
    mongocli atlas clusters search indexes create --clusterName Cluster0 \
      --file episodic_vector_index.json

This module exports all index JSON definitions as Python dicts for easy reference.
Run this file to print all definitions:
  python -m database.atlas_index_definitions

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import json
from typing import Any, Dict, List


# ─────────────────────────────────────────────────────────────────────────────
# VECTOR SEARCH INDEXES  (Atlas knnBeta / vectorSearch type)
# ─────────────────────────────────────────────────────────────────────────────

EPISODIC_VECTOR_INDEX: Dict[str, Any] = {
    "name": "episodic_vector_index",
    "type": "vectorSearch",
    "definition": {
        "fields": [
            {
                "type"        : "vector",
                "path"        : "embedding",
                "numDimensions": 384,          # all-MiniLM-L6-v2 output dim
                "similarity"  : "cosine",
            },
            {
                "type"  : "filter",
                "path"  : "user_id",
            },
            {
                "type"  : "filter",
                "path"  : "decay_score",
            },
        ]
    },
}
"""
How to apply (Atlas UI):
  Collection: episodic_memory
  Index type: Vector Search
  Paste the body of EPISODIC_VECTOR_INDEX["definition"] into the JSON editor.
"""


# ─────────────────────────────────────────────────────────────────────────────
# FULL-TEXT SEARCH INDEXES  (Atlas Search / Lucene BM25)
# ─────────────────────────────────────────────────────────────────────────────

EPISODIC_TEXT_INDEX: Dict[str, Any] = {
    "name": "episodic_text_index",
    "type": "search",
    "definition": {
        "mappings": {
            "dynamic": False,
            "fields": {
                "trigger_description": {
                    "type"     : "string",
                    "analyzer" : "lucene.english",
                },
                "outcome_description": {
                    "type"     : "string",
                    "analyzer" : "lucene.english",
                },
                "category": {
                    "type"     : "string",
                    "analyzer" : "lucene.keyword",
                },
                "user_id": {
                    "type"     : "string",
                    "analyzer" : "lucene.keyword",
                },
            },
        }
    },
}

SEMANTIC_TEXT_INDEX: Dict[str, Any] = {
    "name": "semantic_text_index",
    "type": "search",
    "definition": {
        "mappings": {
            "dynamic": False,
            "fields": {
                "attribute": {
                    "type"     : "string",
                    "analyzer" : "lucene.english",
                },
                "value": {
                    "type"     : "string",
                    "analyzer" : "lucene.english",
                },
                "user_id": {
                    "type"     : "string",
                    "analyzer" : "lucene.keyword",
                },
            },
        }
    },
}

PROCEDURAL_TEXT_INDEX: Dict[str, Any] = {
    "name": "procedural_text_index",
    "type": "search",
    "definition": {
        "mappings": {
            "dynamic": False,
            "fields": {
                "strategy_id": {
                    "type"     : "string",
                    "analyzer" : "lucene.keyword",
                },
                "action_template": {
                    "type"     : "string",
                    "analyzer" : "lucene.english",
                },
                "user_id": {
                    "type"     : "string",
                    "analyzer" : "lucene.keyword",
                },
            },
        }
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# ALL DEFINITIONS (for iteration in atlas_migrations.py)
# ─────────────────────────────────────────────────────────────────────────────

VECTOR_SEARCH_INDEXES: List[Dict[str, Any]] = [
    EPISODIC_VECTOR_INDEX,
]

TEXT_SEARCH_INDEXES: List[Dict[str, Any]] = [
    EPISODIC_TEXT_INDEX,
    SEMANTIC_TEXT_INDEX,
    PROCEDURAL_TEXT_INDEX,
]

ALL_SEARCH_INDEXES = VECTOR_SEARCH_INDEXES + TEXT_SEARCH_INDEXES


# ─────────────────────────────────────────────────────────────────────────────
# CLI USAGE: print all definitions for Atlas UI copy-paste
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("BudgetBandhu — Atlas Index Definitions")
    print("=" * 70)
    print("\nCopy-paste these into Atlas UI → Search Indexes → Create Index\n")

    print("\n--- VECTOR SEARCH INDEXES ---")
    for idx in VECTOR_SEARCH_INDEXES:
        print(f"\nCollection: {idx['name'].split('_')[0]}_memory")
        print(f"Index name: {idx['name']}")
        print("Definition JSON:")
        print(json.dumps(idx["definition"], indent=2))

    print("\n--- FULL-TEXT SEARCH INDEXES ---")
    for idx in TEXT_SEARCH_INDEXES:
        collection = idx["name"].replace("_text_index", "_memory")
        print(f"\nCollection: {collection}")
        print(f"Index name: {idx['name']}")
        print("Definition JSON:")
        print(json.dumps(idx["definition"], indent=2))

    print("\n" + "=" * 70)
    print("NOTE: Regular MongoDB indexes are created automatically by")
    print("      python -m database.atlas_migrations")
    print("=" * 70)
