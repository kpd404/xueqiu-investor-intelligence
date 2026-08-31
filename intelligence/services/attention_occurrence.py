import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    ATTENTION_POLICY_VERSION,
    AssetMentionCandidate,
    AssetReference,
    AssetResolutionResult,
    AssetResolutionStatus,
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceCreate,
    AttentionOccurrenceRebuildResult,
    AttentionOccurrenceWriteResult,
    EffectiveAnalysisPolicy,
    RawEventView,
)
from intelligence.policies.mention_matcher import match_asset_mentions

_EVIDENCE_ORDER = {
    AttentionEvidenceType.OPINION: 0,
    AttentionEvidenceType.EXPLICIT_MENTION: 1,
    AttentionEvidenceType.REPOST: 2,
}


class AttentionRawEventReader(Protocol):
    def get_view(self, event_id: UUID) -> RawEventView | None: ...


class AttentionAssetReader(Protocol):
    def list_mention_candidates(self) -> Sequence[AssetMentionCandidate]: ...


class EffectiveOpinionEntity(Protocol):
    id: UUID
    analysis_id: UUID | None
    asset_id: UUID
    direction: object
    strength: float
    confidence: float


class AttentionOpinionReader(Protocol):
    def list_effective_by_event(
        self,
        event_id: UUID,
        policy: EffectiveAnalysisPolicy,
    ) -> list[EffectiveOpinionEntity]: ...


class AttentionAssetResolver(Protocol):
    def resolve(self, reference: AssetReference) -> AssetResolutionResult: ...


class AttentionOccurrenceWriter(Protocol):
    def replace_for_event(
        self,
        event_id: UUID,
        attention_policy_version: str,
        commands: Sequence[AttentionOccurrenceCreate],
    ) -> AttentionOccurrenceWriteResult: ...


class AttentionUnitOfWork(Protocol):
    raw_events: AttentionRawEventReader
    assets: AttentionAssetReader
    opinions: AttentionOpinionReader
    asset_resolver: AttentionAssetResolver
    attention_occurrences: AttentionOccurrenceWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


AttentionUnitOfWorkFactory = Callable[[], AttentionUnitOfWork]


class AttentionRawEventNotFoundError(LookupError):
    pass


class AttentionOccurrenceService:
    """Rebuild traceable behavior evidence for one immutable RawEvent."""

    def __init__(
        self,
        unit_of_work_factory: AttentionUnitOfWorkFactory,
        effective_analysis_policy: EffectiveAnalysisPolicy,
        *,
        attention_policy_version: str = ATTENTION_POLICY_VERSION,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._effective_analysis_policy = effective_analysis_policy
        self._attention_policy_version = attention_policy_version

    def rebuild_event(self, event_id: UUID) -> AttentionOccurrenceRebuildResult:
        calculated_at = datetime.now(UTC)
        with self._unit_of_work_factory() as unit_of_work:
            event = unit_of_work.raw_events.get_view(event_id)
            if event is None:
                raise AttentionRawEventNotFoundError(f"raw event not found: {event_id}")

            evidence_by_asset: dict[UUID, dict[AttentionEvidenceType, AttentionEvidence]] = {}
            opinion_identity: dict[UUID, tuple[UUID, UUID]] = {}

            for match in match_asset_mentions(
                event.content,
                unit_of_work.assets.list_mention_candidates(),
            ):
                self._add_evidence(
                    evidence_by_asset,
                    match.asset_id,
                    AttentionEvidence(
                        evidence_type=AttentionEvidenceType.EXPLICIT_MENTION,
                        matched_by="DETERMINISTIC_TEXT_MATCH",
                        details={
                            "matches": [item.model_dump(mode="json") for item in match.matches]
                        },
                    ),
                )

            repost_reference = self._repost_reference(event.raw_data)
            if repost_reference is not None:
                reference, details = repost_reference
                resolution = unit_of_work.asset_resolver.resolve(reference)
                if (
                    resolution.status is AssetResolutionStatus.RESOLVED
                    and resolution.asset_id is not None
                ):
                    self._add_evidence(
                        evidence_by_asset,
                        resolution.asset_id,
                        AttentionEvidence(
                            evidence_type=AttentionEvidenceType.REPOST,
                            matched_by=resolution.matched_by or "REPOST_IDENTITY",
                            reference=reference.symbol_hint or reference.name_hint,
                            details=details,
                        ),
                    )

            for opinion in unit_of_work.opinions.list_effective_by_event(
                event_id,
                self._effective_analysis_policy,
            ):
                if opinion.analysis_id is None:
                    continue
                self._add_evidence(
                    evidence_by_asset,
                    opinion.asset_id,
                    AttentionEvidence(
                        evidence_type=AttentionEvidenceType.OPINION,
                        matched_by="ACTIVE_ANALYSIS_OPINION",
                        reference=str(opinion.id),
                        details={
                            "direction": getattr(opinion.direction, "value", opinion.direction),
                            "strength": opinion.strength,
                            "confidence": opinion.confidence,
                        },
                    ),
                )
                opinion_identity[opinion.asset_id] = (opinion.analysis_id, opinion.id)

            commands = [
                AttentionOccurrenceCreate(
                    investor_id=event.investor_id,
                    asset_id=asset_id,
                    event_id=event.id,
                    published_time=event.published_time,
                    evidence_types=tuple(evidence_by_asset[asset_id]),
                    evidence=tuple(
                        sorted(
                            evidence_by_asset[asset_id].values(),
                            key=lambda value: _EVIDENCE_ORDER[value.evidence_type],
                        )
                    ),
                    analysis_id=(
                        opinion_identity[asset_id][0] if asset_id in opinion_identity else None
                    ),
                    opinion_id=(
                        opinion_identity[asset_id][1] if asset_id in opinion_identity else None
                    ),
                    attention_policy_version=self._attention_policy_version,
                    calculated_at=calculated_at,
                )
                for asset_id in sorted(evidence_by_asset, key=lambda value: value.int)
            ]
            write_result = unit_of_work.attention_occurrences.replace_for_event(
                event.id,
                self._attention_policy_version,
                commands,
            )
            unit_of_work.commit()

        return AttentionOccurrenceRebuildResult(
            event_id=event.id,
            occurrence_ids=write_result.occurrence_ids,
            affected_asset_ids=tuple(sorted(evidence_by_asset, key=lambda value: value.int)),
            created_count=write_result.created_count,
            updated_count=write_result.updated_count,
            deleted_count=write_result.deleted_count,
            calculated_at=calculated_at,
        )

    @staticmethod
    def _add_evidence(
        target: dict[UUID, dict[AttentionEvidenceType, AttentionEvidence]],
        asset_id: UUID,
        evidence: AttentionEvidence,
    ) -> None:
        target.setdefault(asset_id, {})[evidence.evidence_type] = evidence

    @classmethod
    def _repost_reference(
        cls,
        raw_data: Mapping[str, object],
    ) -> tuple[AssetReference, dict[str, object]] | None:
        nested = raw_data.get("retweeted_status")
        if not isinstance(nested, Mapping):
            return None

        symbols: set[str] = set()
        symbol_id = nested.get("symbol_id")
        if isinstance(symbol_id, str) and symbol_id.strip():
            symbols.add(symbol_id.strip())
        target = nested.get("target")
        if isinstance(target, str):
            match = re.search(r"/S/([^/]+)", target)
            if match:
                symbols.add(match.group(1))
        extend = nested.get("extend_st_home_page")
        if isinstance(extend, Mapping):
            ai_card = extend.get("ai_card")
            if isinstance(ai_card, Mapping):
                extra = ai_card.get("extra_map")
                if isinstance(extra, Mapping):
                    value = extra.get("symbol")
                    if isinstance(value, str) and value.strip():
                        symbols.add(value.strip())
        if len(symbols) != 1:
            return None

        symbol = next(iter(symbols))
        nested_id = nested.get("id")
        retweet_id = raw_data.get("retweet_status_id")
        return (
            AssetReference(symbol_hint=symbol),
            {
                "symbol_hint": symbol,
                "nested_status_id": str(nested_id) if nested_id is not None else None,
                "retweet_status_id": str(retweet_id) if retweet_id is not None else None,
            },
        )
