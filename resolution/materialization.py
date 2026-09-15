from collections import Counter
from collections.abc import Callable, Collection, Sequence
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts.analysis import EventAnalysisView
from contracts.asset_resolution import (
    AssetResolutionResult,
    AssetResolutionStatus,
    normalize_market_hint,
    normalize_symbol_hint,
)
from contracts.opinion import (
    AssetOpinionExtraction,
    OpinionCreate,
    OpinionWriteResult,
    UnresolvedAsset,
)
from contracts.raw_event import RawEventView
from contracts.recovery import (
    AssetRecoveryResult,
    AssetRecoveryStatus,
)
from contracts.resolution_materialization import (
    CurrentAnalysisResolution,
    CurrentAnalysisResolutionEntry,
    OpinionMaterializationPlan,
)
from resolution.asset_resolver import AssetResolver


class RecoveryAnalysisReader(Protocol):
    def get(self, analysis_id: UUID) -> EventAnalysisView | None: ...

    def get_by_identity(
        self, event_id: UUID, analysis_version: str
    ) -> EventAnalysisView | None: ...


class RecoveryRawEventReader(Protocol):
    def get_view(self, event_id: UUID) -> RawEventView | None: ...


class RecoveryOpinionStore(Protocol):
    def list_by_analysis(self, analysis_id: UUID) -> Sequence[object]: ...

    def add_many(self, commands: Sequence[OpinionCreate]) -> OpinionWriteResult: ...


class RecoveryUnitOfWork(Protocol):
    raw_events: RecoveryRawEventReader
    analyses: RecoveryAnalysisReader
    asset_resolver: AssetResolver
    opinions: RecoveryOpinionStore

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


RecoveryUnitOfWorkFactory = Callable[[], RecoveryUnitOfWork]
ListingIdentity = tuple[str, str]


class AssetRecoveryNotFoundError(LookupError):
    """Raised when the requested EventAnalysis or RawEvent does not exist."""


class OpinionMaterializationService:
    """Project current Asset resolution and materialize Opinions without rewriting Analysis."""

    def __init__(self, unit_of_work_factory: RecoveryUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def plan(
        self,
        *,
        analysis_id: UUID | None = None,
        event_id: UUID | None = None,
        analysis_version: str | None = None,
        allowed_asset_ids: Collection[UUID] | None = None,
        allowed_market_symbols: Collection[ListingIdentity] | None = None,
    ) -> OpinionMaterializationPlan:
        """Build a rollback-only, query-time plan for one Analysis."""

        with self._unit_of_work_factory() as unit_of_work:
            analysis, event = self._load_analysis_and_event(
                unit_of_work,
                analysis_id=analysis_id,
                event_id=event_id,
                analysis_version=analysis_version,
            )
            return self._build_plan(
                unit_of_work,
                analysis,
                event,
                allowed_asset_ids=allowed_asset_ids,
                allowed_market_symbols=allowed_market_symbols,
            )

    def plan_many(
        self,
        *,
        event_ids: Sequence[UUID] = (),
        analysis_ids: Sequence[UUID] = (),
        analysis_version: str | None = None,
        allowed_asset_ids: Collection[UUID] | None = None,
        allowed_market_symbols: Collection[ListingIdentity] | None = None,
    ) -> tuple[OpinionMaterializationPlan, ...]:
        """Build plans for an explicit RawEvent or Analysis delta scope."""

        if not event_ids and not analysis_ids:
            raise ValueError("event_ids or analysis_ids is required")
        if event_ids and not analysis_version:
            raise ValueError("analysis_version is required when event_ids are supplied")

        with self._unit_of_work_factory() as unit_of_work:
            plans: list[OpinionMaterializationPlan] = []
            seen_analysis_ids: set[UUID] = set()
            for requested_analysis_id in analysis_ids:
                analysis, event = self._load_analysis_and_event(
                    unit_of_work,
                    analysis_id=requested_analysis_id,
                    event_id=None,
                    analysis_version=None,
                )
                if analysis.id in seen_analysis_ids:
                    continue
                seen_analysis_ids.add(analysis.id)
                plans.append(
                    self._build_plan(
                        unit_of_work,
                        analysis,
                        event,
                        allowed_asset_ids=allowed_asset_ids,
                        allowed_market_symbols=allowed_market_symbols,
                    )
                )
            for requested_event_id in event_ids:
                analysis, event = self._load_analysis_and_event(
                    unit_of_work,
                    analysis_id=None,
                    event_id=requested_event_id,
                    analysis_version=analysis_version,
                )
                if analysis.id in seen_analysis_ids:
                    continue
                seen_analysis_ids.add(analysis.id)
                plans.append(
                    self._build_plan(
                        unit_of_work,
                        analysis,
                        event,
                        allowed_asset_ids=allowed_asset_ids,
                        allowed_market_symbols=allowed_market_symbols,
                    )
                )
            return tuple(plans)

    def materialize(
        self,
        *,
        analysis_id: UUID | None = None,
        event_id: UUID | None = None,
        analysis_version: str | None = None,
        allowed_asset_ids: Collection[UUID] | None = None,
        allowed_market_symbols: Collection[ListingIdentity] | None = None,
        dry_run: bool = False,
    ) -> AssetRecoveryResult:
        """Materialize only missing resolved Opinion entries in one transaction."""

        with self._unit_of_work_factory() as unit_of_work:
            analysis, event = self._load_analysis_and_event(
                unit_of_work,
                analysis_id=analysis_id,
                event_id=event_id,
                analysis_version=analysis_version,
            )
            plan = self._build_plan(
                unit_of_work,
                analysis,
                event,
                allowed_asset_ids=allowed_asset_ids,
                allowed_market_symbols=allowed_market_symbols,
            )
            extractions = self._extracted_opinions(analysis.structured_output)
            direct_hints = self._direct_unresolved_hints(
                extractions,
                self._unresolved_assets(analysis.structured_output),
            )
            if dry_run:
                return self._result(
                    plan,
                    extractions,
                    direct_hints,
                    write_result=None,
                    dry_run=True,
                )

            commands = self._commands(plan, extractions, event, analysis)
            write_result = unit_of_work.opinions.add_many(commands)
            if commands:
                unit_of_work.commit()
            return self._result(
                plan,
                extractions,
                direct_hints,
                write_result=write_result,
                dry_run=False,
            )

    def materialize_many(
        self,
        *,
        event_ids: Sequence[UUID] = (),
        analysis_ids: Sequence[UUID] = (),
        analysis_version: str | None = None,
        allowed_asset_ids: Collection[UUID] | None = None,
        allowed_market_symbols: Collection[ListingIdentity] | None = None,
        dry_run: bool = False,
    ) -> tuple[AssetRecoveryResult, ...]:
        """Materialize an explicit delta scope one Analysis at a time."""

        plans = self.plan_many(
            event_ids=event_ids,
            analysis_ids=analysis_ids,
            analysis_version=analysis_version,
            allowed_asset_ids=allowed_asset_ids,
            allowed_market_symbols=allowed_market_symbols,
        )
        return tuple(
            self.materialize(
                analysis_id=plan.analysis_id,
                allowed_asset_ids=allowed_asset_ids,
                allowed_market_symbols=allowed_market_symbols,
                dry_run=dry_run,
            )
            for plan in plans
        )

    @staticmethod
    def _load_analysis_and_event(
        unit_of_work: RecoveryUnitOfWork,
        *,
        analysis_id: UUID | None,
        event_id: UUID | None,
        analysis_version: str | None,
    ) -> tuple[EventAnalysisView, RawEventView]:
        if analysis_id is None and (event_id is None or not analysis_version):
            raise ValueError("analysis_id or event_id plus analysis_version is required")

        analysis = (
            unit_of_work.analyses.get(analysis_id)
            if analysis_id is not None
            else unit_of_work.analyses.get_by_identity(event_id, analysis_version or "")
        )
        if analysis is None:
            raise AssetRecoveryNotFoundError("event analysis not found")
        event = unit_of_work.raw_events.get_view(analysis.event_id)
        if event is None:
            raise AssetRecoveryNotFoundError(f"raw event not found: {analysis.event_id}")
        return analysis, event

    def _build_plan(
        self,
        unit_of_work: RecoveryUnitOfWork,
        analysis: EventAnalysisView,
        event: RawEventView,
        *,
        allowed_asset_ids: Collection[UUID] | None,
        allowed_market_symbols: Collection[ListingIdentity] | None,
    ) -> OpinionMaterializationPlan:
        extractions = self._extracted_opinions(analysis.structured_output)
        unresolved = self._unresolved_assets(analysis.structured_output)
        direct_hints = self._direct_unresolved_hints(extractions, unresolved)
        existing_opinions = tuple(unit_of_work.opinions.list_by_analysis(analysis.id))
        existing_by_asset: dict[UUID, object] = {}
        for opinion in sorted(
            existing_opinions,
            key=lambda value: getattr(value, "id", UUID(int=0)).int,
        ):
            asset_id = getattr(opinion, "asset_id", None)
            if isinstance(asset_id, UUID):
                existing_by_asset.setdefault(asset_id, opinion)

        entries: list[CurrentAnalysisResolutionEntry] = []
        materializable_indexes: list[int] = []
        for source_index, extraction in enumerate(extractions):
            resolution = unit_of_work.asset_resolver.resolve(extraction.to_asset_reference())
            existing = (
                existing_by_asset.get(resolution.asset_id)
                if resolution.status is AssetResolutionStatus.RESOLVED
                else None
            )
            allowed = self._is_allowed(
                resolution,
                allowed_asset_ids=allowed_asset_ids,
                allowed_market_symbols=allowed_market_symbols,
            )
            materializable = (
                resolution.status is AssetResolutionStatus.RESOLVED and existing is None and allowed
            )
            entry = self._entry(
                source_kind="EXTRACTED_OPINION",
                source_mention_index=source_index,
                name=extraction.asset_name,
                market=extraction.market,
                symbol=extraction.symbol,
                resolution=resolution,
                existing_opinion_id=getattr(existing, "id", None),
                materializable=materializable,
                materialization_blocked_reason=(
                    "ALREADY_MATERIALIZED"
                    if existing is not None
                    else "NOT_ALLOWLISTED"
                    if resolution.status is AssetResolutionStatus.RESOLVED and not allowed
                    else None
                ),
            )
            entries.append(entry)
            if materializable:
                materializable_indexes.append(len(entries) - 1)

        for source_index, hint in enumerate(direct_hints):
            resolution = unit_of_work.asset_resolver.resolve(hint.to_asset_reference())
            entries.append(
                self._entry(
                    source_kind="DIRECT_UNRESOLVED_HINT",
                    source_mention_index=source_index,
                    name=hint.asset_name,
                    market=hint.market,
                    symbol=hint.symbol,
                    resolution=resolution,
                    materializable=False,
                    materialization_blocked_reason="DIRECT_UNRESOLVED_HINT",
                )
            )

        extracted_entries = entries[: len(extractions)]
        resolved_count = sum(
            entry.outcome is AssetResolutionStatus.RESOLVED for entry in extracted_entries
        )
        unresolved_count = sum(
            entry.outcome is AssetResolutionStatus.UNRESOLVED for entry in extracted_entries
        )
        invalid_count = sum(
            entry.outcome is AssetResolutionStatus.INVALID for entry in extracted_entries
        )
        ambiguous_count = sum(
            entry.outcome is AssetResolutionStatus.AMBIGUOUS for entry in extracted_entries
        )
        projection = CurrentAnalysisResolution(
            analysis_id=analysis.id,
            event_id=event.id,
            persisted_analysis_status=analysis.status,
            extracted_opinion_count=len(extractions),
            direct_unresolved_hint_count=len(direct_hints),
            currently_resolved_count=resolved_count,
            currently_unresolved_count=unresolved_count,
            invalid_count=invalid_count,
            ambiguous_count=ambiguous_count,
            existing_opinion_count=len(existing_opinions),
            materializable_opinion_count=len(materializable_indexes),
            entries=tuple(entries),
        )
        existing_ids = tuple(
            sorted(
                {
                    entry.existing_opinion_id
                    for entry in extracted_entries
                    if entry.existing_opinion_id is not None
                },
                key=lambda value: value.int,
            )
        )
        return OpinionMaterializationPlan(
            analysis_id=analysis.id,
            event_id=event.id,
            persisted_analysis_status=analysis.status,
            projection=projection,
            materializable_entry_indexes=tuple(materializable_indexes),
            already_materialized_opinion_ids=existing_ids,
            calculated_at=analysis.calculated_at,
        )

    @staticmethod
    def _entry(
        *,
        source_kind: str,
        source_mention_index: int,
        name: str,
        market: str | None,
        symbol: str | None,
        resolution: AssetResolutionResult,
        existing_opinion_id: UUID | None = None,
        materializable: bool = False,
        materialization_blocked_reason: str | None = None,
    ) -> CurrentAnalysisResolutionEntry:
        return CurrentAnalysisResolutionEntry(
            source_kind=source_kind,  # type: ignore[arg-type]
            source_mention_index=source_mention_index,
            extracted_name=name,
            extracted_market=market,
            extracted_symbol=symbol,
            outcome=resolution.status,
            asset_id=resolution.asset_id,
            resolved_market=resolution.normalized_market,
            resolved_symbol=resolution.normalized_symbol,
            resolution_basis=resolution.matched_by,
            reason=resolution.reason,
            candidate_asset_ids=resolution.candidate_asset_ids,
            existing_opinion_id=existing_opinion_id,
            materializable=materializable,
            materialization_blocked_reason=materialization_blocked_reason,
        )

    @staticmethod
    def _commands(
        plan: OpinionMaterializationPlan,
        extractions: Sequence[AssetOpinionExtraction],
        event: RawEventView,
        analysis: EventAnalysisView,
    ) -> list[OpinionCreate]:
        commands: list[OpinionCreate] = []
        for entry_index in plan.materializable_entry_indexes:
            entry = plan.projection.entries[entry_index]
            extraction = extractions[entry.source_mention_index]
            if entry.asset_id is None:
                raise RuntimeError("materializable entry did not include asset_id")
            commands.append(
                OpinionCreate(
                    event_id=event.id,
                    analysis_id=analysis.id,
                    investor_id=event.investor_id,
                    asset_id=entry.asset_id,
                    direction=extraction.direction,
                    strength=extraction.strength,
                    confidence=extraction.confidence,
                    thesis=extraction.thesis,
                    catalysts=extraction.catalysts,
                    risks=extraction.risks,
                    time_horizon=extraction.time_horizon,
                    generated_time=analysis.generated_time,
                    model_version=analysis.spec.model_version,
                )
            )
        return commands

    def _result(
        self,
        plan: OpinionMaterializationPlan,
        extractions: Sequence[AssetOpinionExtraction],
        direct_hints: Sequence[UnresolvedAsset],
        *,
        write_result: OpinionWriteResult | None,
        dry_run: bool,
    ) -> AssetRecoveryResult:
        unresolved_assets = self._unresolved_result_assets(
            plan,
            extractions,
            direct_hints,
        )
        created_count = write_result.created_count if write_result is not None else 0
        written_ids = write_result.opinion_ids if write_result is not None else ()
        opinion_ids = tuple(dict.fromkeys((*plan.already_materialized_opinion_ids, *written_ids)))
        reused_count = len(opinion_ids) - created_count
        status = self._status(
            plan,
            unresolved_assets,
            created_count=created_count,
            dry_run=dry_run,
        )
        resolved_asset_ids = tuple(
            dict.fromkeys(
                entry.asset_id
                for entry in plan.projection.entries
                if entry.source_kind == "EXTRACTED_OPINION"
                and entry.outcome is AssetResolutionStatus.RESOLVED
                and entry.asset_id is not None
            )
        )
        return AssetRecoveryResult(
            analysis_id=plan.analysis_id,
            event_id=plan.event_id,
            status=status,
            opinion_ids=opinion_ids,
            created_count=created_count,
            reused_count=reused_count,
            resolved_asset_ids=resolved_asset_ids,
            unresolved_assets=tuple(unresolved_assets),
            calculated_at=plan.calculated_at,
            analysis_status_before=plan.persisted_analysis_status,
            analysis_status_after=plan.persisted_analysis_status,
            projection=plan.projection,
            dry_run=dry_run,
        )

    @staticmethod
    def _status(
        plan: OpinionMaterializationPlan,
        unresolved_assets: Sequence[UnresolvedAsset],
        *,
        created_count: int,
        dry_run: bool,
    ) -> AssetRecoveryStatus:
        if not plan.projection.entries:
            return AssetRecoveryStatus.NO_UNRESOLVED
        if not any(entry.source_kind == "EXTRACTED_OPINION" for entry in plan.projection.entries):
            return (
                AssetRecoveryStatus.UNRESOLVED
                if unresolved_assets
                else AssetRecoveryStatus.NO_UNRESOLVED
            )
        if unresolved_assets:
            return (
                AssetRecoveryStatus.PARTIALLY_RESOLVED
                if plan.projection.currently_resolved_count
                else AssetRecoveryStatus.UNRESOLVED
            )
        if created_count or (dry_run and plan.projection.materializable_opinion_count):
            return AssetRecoveryStatus.RECOVERED
        return AssetRecoveryStatus.ALREADY_RECOVERED

    @staticmethod
    def _unresolved_result_assets(
        plan: OpinionMaterializationPlan,
        extractions: Sequence[AssetOpinionExtraction],
        direct_hints: Sequence[UnresolvedAsset],
    ) -> list[UnresolvedAsset]:
        result: list[UnresolvedAsset] = []
        for entry in plan.projection.entries:
            if entry.outcome is AssetResolutionStatus.RESOLVED:
                continue
            if entry.source_kind == "EXTRACTED_OPINION":
                extraction = extractions[entry.source_mention_index]
                result.append(
                    UnresolvedAsset.from_extraction(
                        extraction,
                        reason=entry.reason or entry.outcome.value,
                        candidate_asset_ids=entry.candidate_asset_ids,
                    )
                )
            else:
                hint = direct_hints[entry.source_mention_index]
                result.append(
                    hint.model_copy(
                        update={
                            "reason": entry.reason or entry.outcome.value,
                            "candidate_asset_ids": entry.candidate_asset_ids,
                        }
                    )
                )
        return result

    @staticmethod
    def _extracted_opinions(output: dict[str, object]) -> tuple[AssetOpinionExtraction, ...]:
        values = output.get("opinions", [])
        if not isinstance(values, (list, tuple)):
            raise ValueError("immutable Analysis opinions must be a list")
        return tuple(AssetOpinionExtraction.model_validate(value) for value in values)

    @staticmethod
    def _unresolved_assets(output: dict[str, object]) -> tuple[UnresolvedAsset, ...]:
        values = output.get("unresolved_assets", [])
        if not isinstance(values, (list, tuple)):
            raise ValueError("immutable Analysis unresolved_assets must be a list")
        return tuple(UnresolvedAsset.model_validate(value) for value in values)

    @classmethod
    def _direct_unresolved_hints(
        cls,
        extractions: Sequence[AssetOpinionExtraction],
        unresolved_assets: Sequence[UnresolvedAsset],
    ) -> tuple[UnresolvedAsset, ...]:
        remaining = Counter(cls._semantic_key(extraction) for extraction in extractions)
        direct: list[UnresolvedAsset] = []
        for unresolved in unresolved_assets:
            key = cls._semantic_key(unresolved)
            if remaining[key]:
                remaining[key] -= 1
            else:
                direct.append(unresolved)
        return tuple(direct)

    @staticmethod
    def _semantic_key(value: object) -> tuple[object, ...]:
        direction = getattr(value, "direction", None)
        return (
            getattr(value, "asset_name", None),
            getattr(value, "market", None),
            getattr(value, "symbol", None),
            getattr(direction, "value", direction),
            getattr(value, "strength", None),
            getattr(value, "confidence", None),
            tuple(getattr(value, "thesis", ())),
            tuple(getattr(value, "catalysts", ())),
            tuple(getattr(value, "risks", ())),
            getattr(value, "time_horizon", None),
        )

    @staticmethod
    def _is_allowed(
        resolution: AssetResolutionResult,
        *,
        allowed_asset_ids: Collection[UUID] | None,
        allowed_market_symbols: Collection[ListingIdentity] | None,
    ) -> bool:
        if allowed_asset_ids is None and allowed_market_symbols is None:
            return True
        if allowed_asset_ids is not None and resolution.asset_id in allowed_asset_ids:
            return True
        if allowed_market_symbols is not None:
            listing = (resolution.normalized_market, resolution.normalized_symbol)
            for market, symbol in allowed_market_symbols:
                if (
                    normalize_market_hint(market) == listing[0]
                    and normalize_symbol_hint(symbol) == listing[1]
                ):
                    return True
        return False


class AssetRecoveryService(OpinionMaterializationService):
    """Compatibility façade for callers migrating from mutable Asset recovery.

    ``recover`` now performs only current-resolution projection and Opinion
    materialization. It never updates EventAnalysis.
    """

    def recover(
        self,
        *,
        analysis_id: UUID | None = None,
        event_id: UUID | None = None,
        analysis_version: str | None = None,
        allowed_asset_ids: Collection[UUID] | None = None,
        allowed_market_symbols: Collection[ListingIdentity] | None = None,
        dry_run: bool = False,
    ) -> AssetRecoveryResult:
        return self.materialize(
            analysis_id=analysis_id,
            event_id=event_id,
            analysis_version=analysis_version,
            allowed_asset_ids=allowed_asset_ids,
            allowed_market_symbols=allowed_market_symbols,
            dry_run=dry_run,
        )


__all__ = [
    "AssetRecoveryNotFoundError",
    "AssetRecoveryService",
    "OpinionMaterializationService",
]
