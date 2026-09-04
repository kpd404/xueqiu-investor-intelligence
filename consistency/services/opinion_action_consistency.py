"""Application service for Opinion × PortfolioAction consistency V0."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from consistency.policies.direction import classify_consistency
from contracts import (
    CONSISTENCY_POLICY_VERSION,
    EffectiveAnalysisPolicy,
    OpinionActionConsistencyCreate,
    OpinionActionConsistencyResult,
    OpinionActionConsistencyView,
    OpinionTimelineEntry,
    PortfolioActionView,
)


class OpinionReader(Protocol):
    def list_effective_timeline(
        self,
        investor_id: UUID,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
    ) -> list[OpinionTimelineEntry]: ...


class ActionReader(Protocol):
    def list_effective_by_investor_asset(
        self,
        investor_id: UUID,
        asset_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> list[PortfolioActionView]: ...


class ConsistencyWriter(Protocol):
    def add_if_absent(
        self,
        artifact: OpinionActionConsistencyCreate,
    ) -> tuple[OpinionActionConsistencyView, bool]: ...


class ConsistencyUnitOfWork(Protocol):
    opinions: OpinionReader
    portfolio_actions: ActionReader
    consistencies: ConsistencyWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


ConsistencyUnitOfWorkFactory = Callable[[], ConsistencyUnitOfWork]


class OpinionActionConsistencyService:
    """Compare active Opinions with fact-time PortfolioAction changes."""

    def __init__(
        self,
        unit_of_work_factory: ConsistencyUnitOfWorkFactory,
        effective_analysis_policy: EffectiveAnalysisPolicy,
        consistency_policy_version: str = CONSISTENCY_POLICY_VERSION,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._effective_analysis_policy = effective_analysis_policy
        self._consistency_policy_version = consistency_policy_version

    def process(
        self,
        investor_id: UUID,
        asset_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> OpinionActionConsistencyResult:
        normalized_as_of = self._normalize_as_of(as_of)
        with self._unit_of_work_factory() as unit_of_work:
            opinions = unit_of_work.opinions.list_effective_timeline(
                investor_id,
                asset_id,
                self._effective_analysis_policy,
            )
            if normalized_as_of is not None:
                opinions = [
                    opinion for opinion in opinions if opinion.published_time <= normalized_as_of
                ]
            actions = unit_of_work.portfolio_actions.list_effective_by_investor_asset(
                investor_id,
                asset_id,
                as_of=normalized_as_of,
            )

            calculated_at = datetime.now(UTC)
            artifact_ids: list[UUID] = []
            unmatched_action_ids: list[UUID] = []
            created_count = 0
            reused_count = 0
            for action in actions:
                opinion = self._latest_opinion_before(opinions, action.effective_time)
                if opinion is None:
                    unmatched_action_ids.append(action.id)
                    continue
                consistency_type, rule_confidence = classify_consistency(
                    opinion.direction,
                    action.action_type,
                )
                confidence = opinion.confidence * rule_confidence
                input_identity = self._input_identity(opinion.opinion_id, action.id)
                artifact, created = unit_of_work.consistencies.add_if_absent(
                    OpinionActionConsistencyCreate(
                        investor_id=investor_id,
                        asset_id=asset_id,
                        opinion_id=opinion.opinion_id,
                        opinion_direction=opinion.direction,
                        portfolio_action_id=action.id,
                        action_type=action.action_type,
                        consistency_type=consistency_type,
                        confidence=confidence,
                        evidence={
                            "opinion_id": str(opinion.opinion_id),
                            "opinion_published_time": opinion.published_time.isoformat(),
                            "action_id": str(action.id),
                            "action_effective_time": action.effective_time.isoformat(),
                            "rule": f"{opinion.direction.value}+{action.action_type.value}",
                        },
                        effective_time=action.effective_time,
                        calculated_at=calculated_at,
                        opinion_analysis_version=self._effective_analysis_policy.active_analysis_version,
                        consistency_policy_version=self._consistency_policy_version,
                        input_identity=input_identity,
                    )
                )
                artifact_ids.append(artifact.id)
                if created:
                    created_count += 1
                else:
                    reused_count += 1
            unit_of_work.commit()

        return OpinionActionConsistencyResult(
            investor_id=investor_id,
            asset_id=asset_id,
            artifact_ids=tuple(artifact_ids),
            unmatched_action_ids=tuple(unmatched_action_ids),
            created_count=created_count,
            reused_count=reused_count,
            calculated_at=calculated_at,
        )

    @staticmethod
    def _latest_opinion_before(
        opinions: list[OpinionTimelineEntry],
        action_time: datetime,
    ) -> OpinionTimelineEntry | None:
        candidates = [opinion for opinion in opinions if opinion.published_time <= action_time]
        return candidates[-1] if candidates else None

    def _input_identity(self, opinion_id: UUID, action_id: UUID) -> str:
        return json.dumps(
            {
                "consistency_policy_version": self._consistency_policy_version,
                "opinion_id": str(opinion_id),
                "portfolio_action_id": str(action_id),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _normalize_as_of(as_of: datetime | None) -> datetime | None:
        if as_of is None:
            return None
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return as_of.astimezone(UTC)


__all__ = ["OpinionActionConsistencyService"]
