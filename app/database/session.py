from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import get_settings


settings = get_settings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(signal_logs)"))}
            if "orderflow_summary_json" not in columns:
                conn.execute(text("ALTER TABLE signal_logs ADD COLUMN orderflow_summary_json TEXT DEFAULT '{}'"))
            if "binance_endpoint_status" not in columns:
                conn.execute(text("ALTER TABLE signal_logs ADD COLUMN binance_endpoint_status TEXT DEFAULT ''"))
            if "market_data_error" not in columns:
                conn.execute(text("ALTER TABLE signal_logs ADD COLUMN market_data_error TEXT DEFAULT ''"))
            signal_defaults = {
                "provider": "TEXT DEFAULT ''",
                "market_type": "TEXT DEFAULT 'USDT Perpetual'",
                "entry_type": "TEXT DEFAULT 'limit'",
                "market_regime": "TEXT DEFAULT ''",
                "analysis_method_json": "TEXT DEFAULT '[]'",
                "derivatives_summary_json": "TEXT DEFAULT '{}'",
                "technical_score": "INTEGER DEFAULT 0",
                "orderflow_score": "INTEGER DEFAULT 0",
                "risk_score": "INTEGER DEFAULT 0",
                "final_confidence": "INTEGER DEFAULT 0",
                "ai_prompt_version": "TEXT DEFAULT ''",
                "active_lessons_json": "TEXT DEFAULT '[]'",
                "orderflow_bias": "TEXT DEFAULT ''",
                "orderflow_conflict": "BOOLEAN DEFAULT 0",
                "absorption_signal": "TEXT DEFAULT 'none'",
                "outcome_status": "TEXT DEFAULT 'pending'",
                "review_status": "TEXT DEFAULT 'not_reviewed'",
            }
            for column, ddl in signal_defaults.items():
                if column not in columns:
                    conn.execute(text(f"ALTER TABLE signal_logs ADD COLUMN {column} {ddl}"))
            of_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(orderflow_snapshots)"))}
            of_defaults = {
                "price": "FLOAT DEFAULT 0",
                "best_bid": "FLOAT DEFAULT 0",
                "best_ask": "FLOAT DEFAULT 0",
                "bid_depth": "FLOAT DEFAULT 0",
                "ask_depth": "FLOAT DEFAULT 0",
                "open_interest": "FLOAT DEFAULT 0",
                "open_interest_change": "FLOAT DEFAULT 0",
                "absorption_signal": "TEXT DEFAULT 'none'",
                "orderflow_bias": "TEXT DEFAULT 'insufficient_data'",
                "orderflow_conflict": "BOOLEAN DEFAULT 0",
                "orderflow_score": "INTEGER DEFAULT 0",
                "flow_interpretation": "TEXT DEFAULT ''",
            }
            for column, ddl in of_defaults.items():
                if of_columns and column not in of_columns:
                    conn.execute(text(f"ALTER TABLE orderflow_snapshots ADD COLUMN {column} {ddl}"))
