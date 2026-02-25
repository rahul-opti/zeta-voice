from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from carriage_services.database.models import Base
from carriage_services.settings import settings

DATABASE_URL = settings.engine.DATABASE_URL

url = make_url(DATABASE_URL)
connect_args = {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables() -> None:
    """Creates all tables defined in the Base metadata."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """Dependency function to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
