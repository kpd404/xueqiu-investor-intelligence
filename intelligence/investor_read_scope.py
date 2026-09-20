"""Shared, immutable Investor-scoped read inputs for Product composition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from config import (
    get_production_analysis_policy,
    get_production_attention_policy_version,
    get_production_thesis_comparison_policy,
    get_settings,
)
from contracts import AttentionOccurrenceView, EffectiveAnalysisPolicy, OpinionTimelineEntry
from contracts.thesis_change import ThesisChangeView
from intelligence.read_scope import AssetReadIdentity


@dataclass(frozen=True, slots=True)
class InvestorReadIdentity:
    investor_id: UUID
    name: str
    platform: str
    platform_user_id: str


@dataclass(frozen=True, slots=True)
class InvestorIntelligenceReadScope:
    """Canonical, read-only inputs for one Investor and one observed window."""

    investor: InvestorReadIdentity
    window_start: datetime
    window_end: datetime
    attention_occurrences: tuple[AttentionOccurrenceView, ...]
    opinions: tuple[OpinionTimelineEntry, ...]
    thesis_changes: tuple[ThesisChangeView, ...]
    assets: tuple[AssetReadIdentity, ...]

    def __post_init__(self) -> None:
        if self.window_start > self.window_end:
            raise ValueError("Investor read scope window is inverted")
        asset_ids = {asset.asset_id for asset in self.assets}
        if any(item.asset_id not in asset_ids for item in self.attention_occurrences):
            raise ValueError("Investor scope contains Attention with missing Asset identity")
        if any(item.asset_id not in asset_ids for item in self.opinions):
            raise ValueError("Investor scope contains Opinion with missing Asset identity")
        if any(item.asset_id not in asset_ids for item in self.thesis_changes):
            raise ValueError("Investor scope contains ThesisChange with missing Asset identity")
        if any(
            item.investor_id != self.investor.investor_id for item in self.attention_occurrences
        ):
            raise ValueError("Investor scope contains Attention from another Investor")
        if any(item.investor_id != self.investor.investor_id for item in self.opinions):
            raise ValueError("Investor scope contains Opinion from another Investor")
        if any(item.investor_id != self.investor.investor_id for item in self.thesis_changes):
            raise ValueError("Investor scope contains ThesisChange from another Investor")

    @property
    def assets_by_id(self) -> dict[UUID, AssetReadIdentity]:
        return {asset.asset_id: asset for asset in self.assets}


class InvestorReader(Protocol):
    def get(self, investor_id: UUID): ...


class AttentionReader(Protocol):
    def list_effective_by_investor(
        self,
        investor_id: UUID,
        policy: EffectiveAnalysisPolicy,
        attention_policy_version: str,
        *,
        as_of: datetime | None = None,
    ) -> list[AttentionOccurrenceView]: ...


class OpinionReader(Protocol):
    def list_effective_timeline_by_investor(
        self,
        investor_id: UUID,
        policy: EffectiveAnalysisPolicy,
        *,
        as_of: datetime | None = None,
    ) -> list[OpinionTimelineEntry]: ...


class ThesisReader(Protocol):
    def list_effective_by_investor(
        self,
        investor_id: UUID,
        policy: EffectiveAnalysisPolicy,
        comparison_version: str | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisChangeView]: ...


class AssetReader(Protocol):
    def list_by_ids(self, asset_ids: tuple[UUID, ...]): ...


class InvestorIntelligenceReadUoW(Protocol):
    investors: InvestorReader
    attention_occurrences: AttentionReader
    opinions: OpinionReader
    thesis_changes: ThesisReader
    assets: AssetReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


InvestorIntelligenceReadUoWFactory = Callable[[], InvestorIntelligenceReadUoW]


class InvestorIntelligenceReadScopeNotFoundError(LookupError):
    """Raised when the requested Investor does not exist."""


class InvestorIntelligenceReadScopeLoader:
    """Load one bounded Investor scope without producing new semantics."""

    def __init__(
        self,
        unit_of_work_factory: InvestorIntelligenceReadUoWFactory,
        *,
        now_factory: Callable[[], datetime] | None = None,
        window_days: int | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self._window_days = window_days or get_settings().context_window_days

    @classmethod
    def from_production(
        cls,
        session_factory: Callable[[], object],
    ) -> InvestorIntelligenceReadScopeLoader:
        from database.unit_of_work import SqlAlchemyInvestorIntelligenceReadUnitOfWork

        return cls(
            lambda: SqlAlchemyInvestorIntelligenceReadUnitOfWork(session_factory),
        )

    def load(
        self,
        investor_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> InvestorIntelligenceReadScope:
        window_end = self._normalize_time(as_of or self._now_factory())
        window_start = window_end - timedelta(days=self._window_days)
        analysis_policy = get_production_analysis_policy().as_effective_policy()
        attention_policy = get_production_attention_policy_version()
        comparison_version = get_production_thesis_comparison_policy().active_analysis_version

        with self._unit_of_work_factory() as unit_of_work:
            investor = unit_of_work.investors.get(investor_id)
            if investor is None:
                raise InvestorIntelligenceReadScopeNotFoundError(
                    f"investor not found: {investor_id}"
                )
            attention = tuple(
                unit_of_work.attention_occurrences.list_effective_by_investor(
                    investor_id,
                    analysis_policy,
                    attention_policy,
                    as_of=window_end,
                )
            )
            opinions = tuple(
                unit_of_work.opinions.list_effective_timeline_by_investor(
                    investor_id,
                    analysis_policy,
                    as_of=window_end,
                )
            )
            thesis_changes = tuple(
                unit_of_work.thesis_changes.list_effective_by_investor(
                    investor_id,
                    analysis_policy,
                    comparison_version,
                    as_of=window_end,
                )
            )
            asset_ids = tuple(
                sorted(
                    {item.asset_id for item in (*attention, *opinions, *thesis_changes)},
                    key=lambda value: value.int,
                )
            )
            assets = tuple(
                AssetReadIdentity(
                    asset_id=asset.id,
                    name=asset.name,
                    market=asset.market,
                    symbol=asset.symbol,
                )
                for asset in unit_of_work.assets.list_by_ids(asset_ids)
            )
            investor_identity = InvestorReadIdentity(
                investor_id=investor.id,
                name=investor.name,
                platform=investor.platform,
                platform_user_id=investor.platform_user_id,
            )

        return InvestorIntelligenceReadScope(
            investor=investor_identity,
            window_start=window_start,
            window_end=window_end,
            attention_occurrences=attention,
            opinions=opinions,
            thesis_changes=thesis_changes,
            assets=assets,
        )

    @staticmethod
    def _normalize_time(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return value.astimezone(UTC)


__all__ = [
    "InvestorIntelligenceReadScope",
    "InvestorIntelligenceReadScopeLoader",
    "InvestorIntelligenceReadScopeNotFoundError",
    "InvestorReadIdentity",
]
