from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import EventAnalysisCreate, EventAnalysisView
from database.models.event_analysis import EventAnalysis


class EventAnalysisRepository:
    """Persistence adapter for one immutable analysis identity's latest result."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_identity(self, event_id: UUID, analysis_version: str) -> EventAnalysisView | None:
        statement = select(EventAnalysis).where(
            EventAnalysis.event_id == event_id,
            EventAnalysis.analysis_version == analysis_version,
        )
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def save(self, command: EventAnalysisCreate) -> EventAnalysisView:
        existing = self._get_entity(command.event_id, command.spec.analysis_version)
        if existing is None:
            entity = EventAnalysis(
                event_id=command.event_id,
                analysis_version=command.spec.analysis_version,
                model_version=command.spec.model_version,
                prompt_version=command.spec.prompt_version,
                schema_version=command.spec.schema_version,
                status=command.status,
                investment_related=command.investment_related,
                generated_time=command.generated_time,
                calculated_at=command.calculated_at,
                confidence=command.confidence,
                structured_output=dict(command.structured_output),
                provider_metadata=dict(command.provider_metadata),
                error_code=command.error_code,
            )
            try:
                with self._session.begin_nested():
                    self._session.add(entity)
                    self._session.flush()
            except IntegrityError:
                existing = self._get_entity(command.event_id, command.spec.analysis_version)
                if existing is None:
                    raise
                entity = existing
            else:
                return self._to_view(entity)

        entity.status = command.status
        entity.model_version = command.spec.model_version
        entity.prompt_version = command.spec.prompt_version
        entity.schema_version = command.spec.schema_version
        entity.investment_related = command.investment_related
        entity.generated_time = command.generated_time
        entity.calculated_at = command.calculated_at
        entity.confidence = command.confidence
        entity.structured_output = dict(command.structured_output)
        entity.error_code = command.error_code
        entity.provider_metadata = dict(command.provider_metadata)
        self._session.flush()
        return self._to_view(entity)

    def _get_entity(self, event_id: UUID, analysis_version: str) -> EventAnalysis | None:
        statement = select(EventAnalysis).where(
            EventAnalysis.event_id == event_id,
            EventAnalysis.analysis_version == analysis_version,
        )
        return self._session.scalar(statement)

    @classmethod
    def _to_view(cls, entity: EventAnalysis) -> EventAnalysisView:
        stored_spec = entity.structured_output.get("analysis_spec")
        provider_metadata = entity.provider_metadata or {}
        provider_id = cls._string_value(
            stored_spec,
            "provider_id",
            provider_metadata.get("provider"),
            "legacy",
        )
        analysis_policy_version = cls._string_value(
            stored_spec,
            "analysis_policy_version",
            None,
            "legacy:unspecified",
        )

        return EventAnalysisView(
            id=entity.id,
            event_id=entity.event_id,
            spec={
                "analysis_version": entity.analysis_version,
                "model_version": entity.model_version,
                "prompt_version": entity.prompt_version,
                "schema_version": entity.schema_version,
                "provider_id": provider_id,
                "analysis_policy_version": analysis_policy_version,
            },
            status=entity.status,
            investment_related=entity.investment_related,
            generated_time=cls._as_utc(entity.generated_time),
            calculated_at=cls._as_utc(entity.calculated_at),
            confidence=entity.confidence,
            structured_output=entity.structured_output,
            error_code=entity.error_code,
            provider_metadata=provider_metadata,
        )

    @staticmethod
    def _string_value(
        source: object,
        key: str,
        fallback: object,
        default: str,
    ) -> str:
        if isinstance(source, Mapping):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
        return default

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
