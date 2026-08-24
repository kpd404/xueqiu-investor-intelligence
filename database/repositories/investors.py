from uuid import UUID

from sqlalchemy.orm import Session

from database.models.investor import Investor


class InvestorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, investor_id: UUID) -> Investor | None:
        return self._session.get(Investor, investor_id)
