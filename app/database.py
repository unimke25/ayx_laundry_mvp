"""
Database configuration for the AYX Laundry MVP.

Why SQLite:
- Zero-config, file-based, perfect for an MVP that needs to ship fast.
- Single-writer limitation is acceptable at MVP scale (low concurrent writes).
- Easy migration path to Postgres later since we use SQLAlchemy's ORM layer
  rather than raw SQL — swapping the connection string is most of the work.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./ayx_laundry.db"

# check_same_thread=False is required for SQLite when used with FastAPI's
# threaded request handling. This is safe here because SQLAlchemy's
# sessionmaker gives each request its own Session.
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and guarantees cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
