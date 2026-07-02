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
            of_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(orderflow_snapshots)"))}
            if of_columns and "best_bid" not in of_columns:
                conn.execute(text("ALTER TABLE orderflow_snapshots ADD COLUMN best_bid FLOAT DEFAULT 0"))
            if of_columns and "best_ask" not in of_columns:
                conn.execute(text("ALTER TABLE orderflow_snapshots ADD COLUMN best_ask FLOAT DEFAULT 0"))
