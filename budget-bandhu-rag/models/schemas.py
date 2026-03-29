# models/schemas.py
"""
Pydantic schemas used across rag/, intelligence/, and api/.
Do NOT import from models/schema.py (SQLAlchemy, deprecated).
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────

class MemoryTier(int, Enum):
    WORKING    = 1
    EPISODIC   = 2
    SEMANTIC   = 3
    PROCEDURAL = 4
    TRAJECTORY = 5


class QueryIntent(str, Enum):
    SIMPLE_LOOKUP  = "SIMPLE_LOOKUP"
    TREND_ANALYSIS = "TREND_ANALYSIS"
    GOAL_PLANNING  = "GOAL_PLANNING"
    SCENARIO_SIM   = "SCENARIO_SIM"
    BEHAVIORAL     = "BEHAVIORAL"
    FULL_ADVISORY  = "FULL_ADVISORY"


class UserReaction(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL  = "neutral"
    UNKNOWN  = "unknown"

class EdgeRelationship(str, Enum):
    IS_A = "IS_A"
    ENABLES = "ENABLES"
    CAUSED_BY = "CAUSED_BY"
    RELATED_TO = "RELATED_TO"

class EpisodicMemory(BaseModel):
    id: str
    user_id: str
    session_id: Optional[str] = None
    event_type: str = "UNKNOWN"
    trigger_description: str = ""
    outcome_description: str = ""
    user_reaction: UserReaction = UserReaction.UNKNOWN
    category: Optional[str] = None
    amount_inr: Optional[float] = None
    embedding: Optional[bytes] = None
    confidence_score: float = 0.5
    decay_score: float = 1.0
    reinforcement_count: int = 0
    created_at: Optional[Any] = None
    last_reinforced: Optional[Any] = None

class SemanticMemory(BaseModel):
    id: str
    user_id: str
    memory_type: str = "UNKNOWN"
    attribute: str = ""
    value: str = ""
    embedding: Optional[bytes] = None
    confidence_score: float = 0.5
    confirmed_count: int = 0
    source_session_ids: List[str] = Field(default_factory=list)
    last_updated: Optional[Any] = None
    created_at: Optional[Any] = None
    
class ProceduralMemory(BaseModel):
    id: str
    user_id: str
    pattern: str = ""
    category: str = ""
    amount: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
class BehavioralArchetype(BaseModel):
    archetype: str

class SavingsTrend(BaseModel):
    trend: str

class TrajectoryMemory(BaseModel):
    id: str
    user_id: str
    
class UnifiedMemoryContext(BaseModel):
    user_id: str
    session_id: str
    query_intent: QueryIntent
    working: Dict[str, Any] = Field(default_factory=dict)
    episodic: List[EpisodicMemory] = []
    semantic: List[SemanticMemory] = []
    graph_paths: List[Any] = []
    procedural: Optional[ProceduralMemory] = None
    trajectory: Optional[TrajectoryMemory] = None
    total_tokens_estimated: int = 0
    tiers_loaded: List[str] = []
    retrieval_time_ms: float = 0.0

class WorkingMemoryItem(BaseModel):
    id: str
    user_id: str
    session_id: str
    content_json: Dict[str, Any]
    content_type: str
    importance_score: float = 0.5

class KnowledgeGraphEdge(BaseModel):
    id: str
    user_id: str
    subject: str = ""
    relation: str = "RELATED_TO"
    object_: str = ""

# ── RAG pipeline models ───────────────────────────────────────

class RetrievedChunk(BaseModel):
    chunk_id:    str
    source_tier: MemoryTier
    content:     str
    score:       float = 0.5
    embedding:   Optional[bytes] = None   # pickled np.ndarray for CRAG cosine
    metadata:    Dict[str, Any]  = Field(default_factory=dict)


class GradedChunk(BaseModel):
    chunk_id:            str
    source_tier:         MemoryTier
    content:             str
    original_score:      float
    crag_score:          float
    token_overlap:       float
    semantic_similarity: float
    entity_match:        float
    decision:            str            # "KEEP" | "TRIM" | "DISCARD"
    trimmed_content:     Optional[str] = None
    metadata:            Dict[str, Any] = Field(default_factory=dict)


class RouteDecision(BaseModel):
    intent:            QueryIntent
    tiers_to_query:    List[int]
    use_simulation:    bool
    use_llm:           bool
    db_direct:         bool
    confidence:        float
    matched_keywords:  List[str] = Field(default_factory=list)


class SelfRAGVerdict(BaseModel):
    passed:               bool
    failed_criteria:      List[str]     = Field(default_factory=list)
    retry_instruction:    Optional[str] = None
    grounded_score:       float = 1.0
    retrieval_used_score: float = 1.0
    hallucination_score:  float = 0.0
    usefulness_score:     float = 1.0


# ── API request/response models ───────────────────────────────

class ChatRequest(BaseModel):
    user_id:         str
    query:           str
    session_id:      Optional[str]            = "default"
    session_context: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    response:           str
    session_id:         str
    confidence:         float
    memory_used:        Dict[str, Any]
    gates_passed:       bool
    conversation_turns: int
    intent:             Optional[str] = None
    rag_quality:        Optional[str] = None


class TransactionCreate(BaseModel):
    user_id:          str
    description:      str
    amount:           float
    transaction_type: str = "Debit"
    date:             Optional[str] = None
    category:         Optional[str] = None


class TransactionResponse(BaseModel):
    transaction_id:   str
    category:         str
    is_anomaly:       bool
    anomaly_score:    float
    anomaly_severity: str
    message:          str = "Transaction added"
