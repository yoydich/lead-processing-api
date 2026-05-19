import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

raw_database_url = os.getenv("DATABASE_URL")
is_railway = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))

if is_railway and (
    not raw_database_url or raw_database_url.startswith("sqlite")
):
    raise RuntimeError(
        "Persistent DATABASE_URL is required on Railway. "
        "Attach a Railway PostgreSQL service and expose DATABASE_URL to this app."
    )

DATABASE_URL = raw_database_url or "sqlite:///./leads.db"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

if DATABASE_URL.startswith("sqlite:///"):
    sqlite_path = DATABASE_URL.removeprefix("sqlite:///")
    if sqlite_path and sqlite_path != ":memory:":
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
