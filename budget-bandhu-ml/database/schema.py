"""
Production Database Schema
Supports: User profiles, memories, conversations, transactions

Author: Aryan Lomte
Date: Jan 16, 2026
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json

Base = declarative_base()


class User(Base):
    """User account"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    semantic_memories = relationship("SemanticMemory", back_populates="user", cascade="all, delete-orphan")
    episodic_memories = relationship("EpisodicMemory", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")


class SemanticMemory(Base):
    """User profile attributes (long-term facts)"""
    __tablename__ = 'semantic_memories'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    attribute_type = Column(String(50), nullable=False)  # 'monthly_income', 'risk_profile', etc.
    value = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="semantic_memories")


class EpisodicMemory(Base):
    """User events (timestamped experiences)"""
    __tablename__ = 'episodic_memories'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    event_summary = Column(Text, nullable=False)
    trigger_type = Column(String(50))  # 'expense', 'income', 'goal', 'overspend', etc.
    meta_data = Column(Text)  # JSON string
    timestamp = Column(DateTime, default=datetime.utcnow)
    relevance_score = Column(Float, default=1.0)  # For memory decay
    
    user = relationship("User", back_populates="episodic_memories")


class Conversation(Base):
    """Conversation sessions"""
    __tablename__ = 'conversations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    session_id = Column(String(100), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """Individual messages in a conversation"""
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey('conversations.id'), nullable=False)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    confidence = Column(Float)  # For assistant messages
    meta_data = Column(Text)  # JSON string (latency, model version, etc.)
    
    conversation = relationship("Conversation", back_populates="messages")


class Transaction(Base):
    """Financial transactions"""
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    description = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String(50))
    transaction_type = Column(String(20))  # 'income' or 'expense'
    date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="transactions")


# Database initialization
class DatabaseManager:
    def __init__(self, db_url: str = "sqlite:///budget_bandhu.db"):
        """
        Initialize database connection
        
        Args:
            db_url: Database URL
                - SQLite: "sqlite:///budget_bandhu.db"
                - PostgreSQL: "postgresql://user:pass@localhost/dbname"
        """
        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
    def create_tables(self):
        """Create all tables"""
        Base.metadata.create_all(self.engine)
        print("[DB] ✅ All tables created")
    
    def get_session(self):
        """Get a new database session"""
        return self.SessionLocal()
    
    def drop_all_tables(self):
        """Drop all tables (use with caution!)"""
        Base.metadata.drop_all(self.engine)
        print("[DB] ⚠️  All tables dropped")


# Initialize database
if __name__ == "__main__":
    db = DatabaseManager()
    db.create_tables()
    print("Database initialized successfully!")
