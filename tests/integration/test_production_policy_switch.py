from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from contracts import (
    AnalysisSpec,
    AttentionEvidenceType,
    EffectiveAnalysisPolicy,
    EventAnalysisStatus,
    OpinionDirection,
)
from database.models import (
    AttentionOccurrence,
    EventAnalysis,
    Investor,
    InvestorAssetState,
    InvestorAssetStateChange,
    Opinion,
    RawEvent,
)
from database.repositories import (
    AttentionOccurrenceRepository,
    InvestorAssetStateChangeRepository,
    InvestorAssetStateRepository,
)

OLD_SPEC = AnalysisSpec.from_model_version("policy-switch-v4")
NEW_SPEC = AnalysisSpec.from_model_version("policy-switch-v5")
OLD_POLICY = EffectiveAnalysisPolicy(active_spec=OLD_SPEC)
NEW_POLICY = EffectiveAnalysisPolicy(active_spec=NEW_SPEC)


def _event(session: Session, investor: Investor, suffix: str, published_time: datetime) -> RawEvent:
    event = RawEvent(
        investor_id=investor.id,
        event_type="POST",
        source="manual",
        url=f"https://example.test/policy-switch/{suffix}",
        published_time=published_time,
        content="Asset view",
        raw_data={},
        hash=uuid4().hex + uuid4().hex,
        collected_time=published_time,
    )
    session.add(event)
    session.flush()
    return event


def _opinion(
    session: Session,
    *,
    event: RawEvent,
    asset_id,
    spec: AnalysisSpec,
    direction: OpinionDirection,
) -> tuple[EventAnalysis, Opinion]:
    analysis = EventAnalysis(
        event_id=event.id,
        analysis_version=spec.analysis_version,
        model_version=spec.model_version,
        prompt_version=spec.prompt_version,
        schema_version=spec.schema_version,
        status=EventAnalysisStatus.SUCCESS,
        investment_related=True,
        generated_time=event.published_time,
        calculated_at=event.published_time,
        confidence=0.8,
        structured_output={"analysis_spec": spec.model_dump(mode="json")},
        provider_metadata={},
    )
    session.add(analysis)
    session.flush()
    opinion = Opinion(
        event_id=event.id,
        analysis_id=analysis.id,
        investor_id=event.investor_id,
        asset_id=asset_id,
        direction=direction,
        strength=70,
        confidence=0.8,
        thesis=["policy switch"],
        catalysts=[],
        risks=[],
        generated_time=event.published_time,
        model_version=spec.model_version,
    )
    session.add(opinion)
    session.flush()
    return analysis, opinion


def _state(session: Session, investor_id, asset_id) -> InvestorAssetState:
    state = InvestorAssetState(
        investor_id=investor_id,
        asset_id=asset_id,
        mention_count=1,
        last_activity_time=datetime(2026, 9, 1, tzinfo=UTC),
        last_material_change_time=datetime(2026, 9, 1, tzinfo=UTC),
    )
    session.add(state)
    session.flush()
    return state


def _state_change(
    session: Session,
    *,
    opinion: Opinion,
    investor_id,
    asset_id,
    effective_time: datetime,
) -> InvestorAssetStateChange:
    change = InvestorAssetStateChange(
        investor_id=investor_id,
        asset_id=asset_id,
        transition_type="NEW_ATTENTION",
        effective_time=effective_time,
        calculated_at=effective_time,
        before=None,
        after={
            "investor_id": str(investor_id),
            "asset_id": str(asset_id),
            "attention_level": "DISCOVERED",
            "direction": "BULLISH",
            "conviction": 56,
            "mention_count": 1,
            "position_status": "NO_POSITION",
            "last_activity_time": effective_time.isoformat(),
            "last_material_change_time": effective_time.isoformat(),
        },
        triggering_opinion_id=opinion.id,
        source_event_ids=[str(opinion.event_id)],
        state_policy_version="state-v1",
    )
    session.add(change)
    session.flush()
    return change


def _occurrence(
    session: Session,
    *,
    event: RawEvent,
    asset_id,
    analysis_id,
    opinion_id,
) -> AttentionOccurrence:
    occurrence = AttentionOccurrence(
        investor_id=event.investor_id,
        asset_id=asset_id,
        event_id=event.id,
        published_time=event.published_time,
        evidence_types=[AttentionEvidenceType.OPINION.value],
        evidence=[
            {
                "evidence_type": AttentionEvidenceType.OPINION.value,
                "matched_by": "fixture",
                "reference": str(opinion_id),
                "details": {},
            }
        ],
        analysis_id=analysis_id,
        opinion_id=opinion_id,
        attention_policy_version="attention-occurrence-v1",
        calculated_at=event.published_time,
    )
    session.add(occurrence)
    session.flush()
    return occurrence


def test_policy_switch_scopes_state_changes_states_and_attention(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory() as session:
        active_investor = Investor(
            name="Active policy investor",
            platform="manual",
            platform_user_id="policy-active",
        )
        old_only_investor = Investor(
            name="Old-only policy investor",
            platform="manual",
            platform_user_id="policy-old-only",
        )
        from database.models import Asset

        active_asset = Asset(name="Active asset", market="SH", symbol="A1")
        old_only_asset = Asset(name="Old-only asset", market="SH", symbol="A2")
        session.add_all([active_investor, old_only_investor, active_asset, old_only_asset])
        session.flush()

        both_event = _event(
            session,
            active_investor,
            "both",
            datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
        )
        old_analysis, old_opinion = _opinion(
            session,
            event=both_event,
            asset_id=active_asset.id,
            spec=OLD_SPEC,
            direction=OpinionDirection.BEARISH,
        )
        new_analysis, new_opinion = _opinion(
            session,
            event=both_event,
            asset_id=active_asset.id,
            spec=NEW_SPEC,
            direction=OpinionDirection.BULLISH,
        )
        old_only_event = _event(
            session,
            old_only_investor,
            "old-only",
            datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        )
        _, old_only_opinion = _opinion(
            session,
            event=old_only_event,
            asset_id=old_only_asset.id,
            spec=OLD_SPEC,
            direction=OpinionDirection.BULLISH,
        )
        active_event = _event(
            session,
            active_investor,
            "new-only",
            datetime(2026, 9, 1, 11, 0, tzinfo=UTC),
        )
        active_only_analysis, active_only_opinion = _opinion(
            session,
            event=active_event,
            asset_id=active_asset.id,
            spec=NEW_SPEC,
            direction=OpinionDirection.BULLISH,
        )
        _state(session, active_investor.id, active_asset.id)
        _state(session, old_only_investor.id, old_only_asset.id)
        old_change = _state_change(
            session,
            opinion=old_opinion,
            investor_id=active_investor.id,
            asset_id=active_asset.id,
            effective_time=both_event.published_time,
        )
        new_change = _state_change(
            session,
            opinion=new_opinion,
            investor_id=active_investor.id,
            asset_id=active_asset.id,
            effective_time=both_event.published_time,
        )
        old_only_change = _state_change(
            session,
            opinion=old_only_opinion,
            investor_id=old_only_investor.id,
            asset_id=old_only_asset.id,
            effective_time=old_only_event.published_time,
        )
        old_occurrence = _occurrence(
            session,
            event=both_event,
            asset_id=active_asset.id,
            analysis_id=old_analysis.id,
            opinion_id=old_opinion.id,
        )
        new_occurrence = _occurrence(
            session,
            event=active_event,
            asset_id=active_asset.id,
            analysis_id=active_only_analysis.id,
            opinion_id=active_only_opinion.id,
        )
        session.commit()

    with db_session_factory() as session:
        state_changes = InvestorAssetStateChangeRepository(session)
        old_changes = state_changes.list_effective(OLD_POLICY)
        new_changes = state_changes.list_effective(NEW_POLICY)
        assert {row.id for row in old_changes} == {
            old_change.id,
            old_only_change.id,
        }
        assert {row.id for row in new_changes} == {new_change.id}
        assert new_changes[0].analysis_id == new_analysis.id
        assert new_changes[0].analysis_version == NEW_SPEC.analysis_version

        states = InvestorAssetStateRepository(session)
        assert {row.id for row in states.list_effective(OLD_POLICY)} == {
            session.scalar(
                select(InvestorAssetState.id).where(
                    InvestorAssetState.investor_id == old_only_investor.id
                )
            ),
            session.scalar(
                select(InvestorAssetState.id).where(
                    InvestorAssetState.investor_id == active_investor.id
                )
            ),
        }
        new_state_rows = states.list_effective(NEW_POLICY)
        assert len(new_state_rows) == 1
        assert new_state_rows[0].investor_id == active_investor.id

        occurrences = AttentionOccurrenceRepository(session)
        old_occurrences = occurrences.list_effective(OLD_POLICY)
        new_occurrences = occurrences.list_effective(NEW_POLICY)
        assert {row.id for row in old_occurrences} == {old_occurrence.id}
        assert {row.id for row in new_occurrences} == {new_occurrence.id}
