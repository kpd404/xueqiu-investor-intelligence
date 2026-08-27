from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models.investor import Investor


class InvestorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, investor_id: UUID) -> Investor | None:
        return self._session.get(Investor, investor_id)

    def get_by_platform_user_id(self, platform: str, platform_user_id: str) -> Investor | None:
        normalized_platform, normalized_user_id = self._normalize_identity(
            platform, platform_user_id
        )
        statement = select(Investor).where(
            Investor.platform == normalized_platform,
            Investor.platform_user_id == normalized_user_id,
        )
        return self._session.scalar(statement)

    def get_or_create(
        self,
        *,
        platform: str,
        platform_user_id: str,
        name: str,
        homepage_url: str | None = None,
    ) -> tuple[Investor, bool]:
        normalized_platform, normalized_user_id = self._normalize_identity(
            platform, platform_user_id
        )
        existing = self.get_by_platform_user_id(normalized_platform, normalized_user_id)
        if existing is not None:
            return existing, False

        investor = Investor(
            name=name.strip() or normalized_user_id,
            platform=normalized_platform,
            platform_user_id=normalized_user_id,
            homepage_url=homepage_url,
        )
        try:
            with self._session.begin_nested():
                self._session.add(investor)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_platform_user_id(normalized_platform, normalized_user_id)
            if existing is None:
                raise
            return existing, False
        return investor, True

    @staticmethod
    def _normalize_identity(platform: str, platform_user_id: str) -> tuple[str, str]:
        normalized_platform = platform.strip().lower()
        normalized_user_id = platform_user_id.strip()
        if not normalized_platform:
            raise ValueError("platform must not be blank")
        if not normalized_user_id:
            raise ValueError("platform_user_id must not be blank")
        return normalized_platform, normalized_user_id
