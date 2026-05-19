import os
import logging
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

logger = logging.getLogger(__name__)


def _build_postgres_url_from_parts() -> str | None:
    host = os.getenv("PGHOST") or os.getenv("POSTGRES_HOST")
    database = os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB")
    user = os.getenv("PGUSER") or os.getenv("POSTGRES_USER")
    password = os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD")
    port = os.getenv("PGPORT") or os.getenv("POSTGRES_PORT") or "5432"

    if not all([host, database, user, password]):
        return None

    return (
        "postgresql+psycopg://"
        f"{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}"
    )


CONFIG_SOURCE = "default"
raw_database_url = os.getenv("DATABASE_URL")

if raw_database_url:
    CONFIG_SOURCE = "env:DATABASE_URL"
else:
    raw_database_url = os.getenv("DATABASE_PRIVATE_URL")
    if raw_database_url:
        CONFIG_SOURCE = "env:DATABASE_PRIVATE_URL"
    else:
        raw_database_url = _build_postgres_url_from_parts()
        if raw_database_url:
            CONFIG_SOURCE = "env:PGPARTS"

is_railway = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))

if is_railway and not raw_database_url:
    logger.error(
        "No persistent database config found on Railway. Falling back to SQLite, "
        "which is ephemeral and will lose leads after redeploy/restart. Set "
        "DATABASE_URL on the web service, for example ${{Postgres.DATABASE_URL}}."
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


def database_backend() -> str:
    if DATABASE_URL.startswith("sqlite"):
        return "sqlite"
    if DATABASE_URL.startswith("postgresql"):
        return "postgresql"
    return DATABASE_URL.split(":", 1)[0]


def is_persistent_database() -> bool:
    return database_backend() != "sqlite"


def database_config_source() -> str:
    return CONFIG_SOURCE


def is_railway_environment() -> bool:
    return is_railway


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
