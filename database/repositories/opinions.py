from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import OpinionCreate, OpinionWriteResult
from database.models.opinion import Opinion


class OpinionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_event(self, event_id: UUID) -> list[Opinion]:
        statement = select(Opinion).where(Opinion.event_id == event_id).order_by(Opinion.id)
        return list(self._session.scalars(statement))

    def exists(self, event_id: UUID, asset_id: UUID, model_version: str) -> bool:
        return self._get_by_identity(event_id, asset_id, model_version) is not None

    def add_many(self, commands: Sequence[OpinionCreate]) -> OpinionWriteResult:
        opinion_ids: list[UUID] = []
        created_count = 0

        for command in commands:
            existing = self._get_by_identity(
                command.event_id,
                command.asset_id,
                command.model_version,
            )
            if existing is not None:
                opinion_ids.append(existing.id)
                continue

            opinion = Opinion(
                event_id=command.event_id,
                investor_id=command.investor_id,
                asset_id=command.asset_id,
                direction=command.direction,
                strength=command.strength,
                confidence=command.confidence,
                thesis=list(command.thesis),
                catalysts=list(command.catalysts),
                risks=list(command.risks),
                time_horizon=command.time_horizon,
                generated_time=command.generated_time,
                model_version=command.model_version,
            )

            try:
                with self._session.begin_nested():
                    self._session.add(opinion)
                    self._session.flush()
            except IntegrityError:
                existing = self._get_by_identity(
                    command.event_id,
                    command.asset_id,
                    command.model_version,
                )
                if existing is None:
                    raise
                opinion_ids.append(existing.id)
                continue

            opinion_ids.append(opinion.id)
            created_count += 1

        return OpinionWriteResult(
            opinion_ids=tuple(opinion_ids),
            created_count=created_count,
        )

    def _get_by_identity(
        self,
        event_id: UUID,
        asset_id: UUID,
        model_version: str,
    ) -> Opinion | None:
        statement = select(Opinion).where(
            Opinion.event_id == event_id,
            Opinion.asset_id == asset_id,
            Opinion.model_version == model_version,
        )
        return self._session.scalar(statement)
