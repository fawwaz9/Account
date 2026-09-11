import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# app/_database/db.py -> app/_database -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "app.db"

# Anchored to the backend directory rather than the process's working
# directory. The old "sqlite:///./app.db" default resolved against wherever
# uvicorn happened to be started, so a local run wrote to backend/app.db while
# docker-compose (DATABASE_URL=sqlite:////app/data/app.db, bind-mounted from
# backend/data) used a different file entirely, and the two silently diverged.
DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()