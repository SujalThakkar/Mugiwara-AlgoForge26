"""
Initialize Production Database
Creates tables and populates initial demo data if needed.

Run: python initialize_db.py
"""
import sys
import os

# Add root directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.schema import DatabaseManager, User

def init_db():
    print("🚀 Initializing Budget Bandhu Database...")
    
    # Use environment variable or default to SQLite
    db_url = os.getenv("DATABASE_URL", "sqlite:///budget_bandhu_production.db")
    print(f"   Target: {db_url}")
    
    db_manager = DatabaseManager(db_url)
    
    # 1. Create Tables
    print("\n1. Creating tables...")
    try:
        db_manager.create_tables()
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return

    # 2. Create Demo User
    print("\n2. Creating demo user...")
    session = db_manager.get_session()
    try:
        demo_user_id = 1
        user = session.query(User).filter_by(id=demo_user_id).first()
        if not user:
            user = User(id=demo_user_id, username="demo_user", email="demo@example.com")
            session.add(user)
            session.commit()
            print(f"✅ Demo user created (ID: {demo_user_id})")
        else:
            print(f"ℹ️  Demo user already exists (ID: {demo_user_id})")
            
    except Exception as e:
        print(f"❌ Error creating demo user: {e}")
    finally:
        session.close()

    print("\n✨ Database initialization complete!")
    print(f"   Database file: budget_bandhu.db")

if __name__ == "__main__":
    init_db()
