from collections.abc import Callable
from types import TracebackType

from sqlalchemy.orm import Session

from database.repositories import AssetRepository, OpinionRepository, RawEventRepository


class SqlAlchemyOpinionUnitOfWork:
    """Short-lived repository scope used before and after extractor calls."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlAlchemyOpinionUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.raw_events = RawEventRepository(self._session)
        self.assets = AssetRepository(self._session)
        self.opinions = OpinionRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True

    def rollback(self) -> None:
        if self._session is not None:
            self._session.rollback()
