from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: opens a database session per request and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_missing_columns(bind=engine) -> None:
    """Tiny migration for databases created before a column existed.

    `create_all` only creates missing tables, so columns added later are added here.
    """
    columns = {c["name"] for c in inspect(bind).get_columns("transactions")}
    with bind.begin() as conn:
        if "reference" not in columns:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN reference VARCHAR(64)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_transactions_reference ON transactions (reference)"))
