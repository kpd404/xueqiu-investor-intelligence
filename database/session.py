from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings


def create_database_engine(database_url: str | None = None) -> Engine:
    settings = get_settings()
    url = database_url or settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(
        url,
        echo=settings.database_echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


engine = create_database_engine()
SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Provide a transaction-scoped database session to application code."""

    with SessionFactory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
