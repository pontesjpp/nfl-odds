import os
import sqlite3
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///data/nfl_odds.db"

engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now)
    game_id = Column(String, index=True)
    player_name = Column(String, index=True)
    bookmaker = Column(String, index=True)
    market = Column(String, index=True)
    line = Column(Float)
    side = Column(String) # 'over' or 'under'
    odds = Column(Float)

class ModelPrediction(Base):
    __tablename__ = "model_predictions"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now)
    game_id = Column(String, index=True)
    player_name = Column(String, index=True)
    market = Column(String)
    line = Column(Float)
    predicted_probability = Column(Float)
    fair_odds = Column(Float)
    model_version = Column(String)

class Bet(Base):
    __tablename__ = "bets"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now)
    season = Column(Integer, default=2026)
    week = Column(Integer, default=1)
    game_id = Column(String, nullable=True)
    player_name = Column(String, index=True)
    team = Column(String, nullable=True)
    opponent = Column(String, nullable=True)
    bookmaker = Column(String, default="Betclic")
    market = Column(String, index=True)
    line = Column(Float)
    side = Column(String) # 'over' or 'under'
    odds = Column(Float)
    units = Column(Float, default=1.0)
    base_units = Column(Float, default=1.0)
    ai_multiplier = Column(Float, default=1.0)
    ai_sizing_rationale = Column(String, nullable=True)
    side_favorability = Column(String, nullable=True)
    ai_summary = Column(String, nullable=True)
    model_probability = Column(Float, nullable=True)
    implied_probability = Column(Float, nullable=True)
    edge = Column(Float, nullable=True)
    ev_percent = Column(Float, nullable=True)
    actual_value = Column(Float, nullable=True)
    result = Column(String, default="pending") # 'pending', 'won', 'lost', 'push'
    profit_units = Column(Float, default=0.0)
    settled_at = Column(DateTime, nullable=True)
    portfolio_type = Column(String, default="safe", index=True)
    is_locked = Column(Boolean, default=False)
    notes = Column(String, nullable=True)

def migrate_db():
    """Garante que colunas novas sejam adicionadas sem perda de dados no SQLite existente."""
    db_path = "data/nfl_odds.db"
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(bets)")
        existing_cols = set(r[1] for r in cursor.fetchall())
        
        new_cols = [
            ("base_units", "FLOAT DEFAULT 1.0"),
            ("ai_multiplier", "FLOAT DEFAULT 1.0"),
            ("ai_sizing_rationale", "TEXT"),
            ("side_favorability", "TEXT"),
            ("ai_summary", "TEXT")
        ]
        
        for col_name, col_type in new_cols:
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE bets ADD COLUMN {col_name} {col_type}")
                print(f"-> Migração: Coluna '{col_name}' adicionada à tabela bets.")
                
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Migração de banco: {e}")

def init_db():
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    migrate_db()
    print("Banco de dados inicializado e sincronizado com sucesso em data/nfl_odds.db!")

if __name__ == "__main__":
    init_db()
