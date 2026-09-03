from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from consistency import OpinionActionConsistencyService
from contracts import (
    AnalysisSpec,
    ConsistencyType,
    EffectiveAnalysisPolicy,
    EventAnalysisStatus,
    EventType,
    OpinionDirection,
    PortfolioDTO,
    PortfolioSnapshotBatchDTO,
    PositionSnapshotDTO,
)
from database.models import (
    Asset,
    EventAnalysis,
    Investor,
    InvestorActionConsistency,
    Opinion,
    RawEvent,
)
from database.repositories import (
    InvestorActionConsistencyRepository,
    PortfolioRepository,
    PortfolioSnapshotBatchRepository,
    PositionSnapshotRepository,
)
from database.unit_of_work import (
    SqlAlchemyConsistencyUnitOfWork,
    SqlAlchemyPortfolioUnitOfWork,
)
from portfolio import PositionChangeDetectionService

ACTIVE_SPEC = AnalysisSpec.from_model_version("consistency-active-v1")
OLD_SPEC = AnalysisSpec.from_model_version("consistency-old-v1")
POLICY = EffectiveAnalysisPolicy(active_spec=ACTIVE_SPEC)
PREVIOUS_TIME = datetime(2026, 9, 3, 10, tzinfo=UTC)
CURRENT_TIME = datetime(2026, 9, 4, 10, tzinfo=UTC)


def _seed_case(
    factory: sessionmaker[Session],
    *,
    direction: OpinionDirection,
    previous_weight: float | None,
    current_weight: float | None,
    analysis_spec: AnalysisSpec = ACTIVE_SPEC,
    opinion_time: datetime = PREVIOUS_TIME,
) -> tuple[UUID, UUID, UUID, UUID]:
    with factory() as session:
        investor = Investor(
            name="Consistency Investor",
            platform="manual",
            platform_user_id=f"consistency-{uuid4()}",
        )
        asset = Asset(name="Consistency Asset", market="SH", symbol=f"CON{uuid4().hex[:6]}")
        session.add_all([investor, asset])
        session.flush()
        portfolio = PortfolioRepository(session).create(
            PortfolioDTO(
                investor_id=investor.id,
                source="manual",
                external_id=f"portfolio-{uuid4()}",
                name="Consistency Portfolio",
            )
        )
        batches = PortfolioSnapshotBatchRepository(session)
        previous_batch, _ = batches.get_or_create(
            PortfolioSnapshotBatchDTO(
                portfolio_id=portfolio.id,
                snapshot_time=PREVIOUS_TIME,
                source="manual",
                external_id="snapshot-previous",
            )
        )
        current_batch, _ = batches.get_or_create(
            PortfolioSnapshotBatchDTO(
                portfolio_id=portfolio.id,
                snapshot_time=CURRENT_TIME,
                source="manual",
                external_id="snapshot-current",
            )
        )
        snapshots = PositionSnapshotRepository(session)
        if previous_weight is not None:
            snapshots.create(
                PositionSnapshotDTO(
                    portfolio_id=portfolio.id,
                    snapshot_batch_id=previous_batch.id,
                    asset_id=asset.id,
                    weight=previous_weight,
                    snapshot_time=PREVIOUS_TIME,
                    source_type="manual",
                    source_reference="previous-position",
                )
            )
        if current_weight is not None:
            snapshots.create(
                PositionSnapshotDTO(
                    portfolio_id=portfolio.id,
                    snapshot_batch_id=current_batch.id,
                    asset_id=asset.id,
                    weight=current_weight,
                    snapshot_time=CURRENT_TIME,
                    source_type="manual",
                    source_reference="current-position",
                )
            )

        event = RawEvent(
            investor_id=investor.id,
            event_type=EventType.POST,
            source="manual",
            url=f"https://example.test/consistency/{uuid4()}",
            published_time=opinion_time,
            content="Consistency opinion evidence",
            raw_data={},
            hash=uuid4().hex + uuid4().hex,
            collected_time=CURRENT_TIME,
        )
        session.add(event)
        session.flush()
        analysis = EventAnalysis(
            event_id=event.id,
            analysis_version=analysis_spec.analysis_version,
            model_version=analysis_spec.model_version,
            prompt_version=analysis_spec.prompt_version,
            schema_version=analysis_spec.schema_version,
            status=EventAnalysisStatus.SUCCESS,
            investment_related=True,
            generated_time=opinion_time + timedelta(hours=1),
            calculated_at=opinion_time + timedelta(hours=1),
            confidence=0.8,
            structured_output={"analysis_spec": analysis_spec.model_dump(mode="json")},
            provider_metadata={},
        )
        session.add(analysis)
        session.flush()
        opinion = Opinion(
            event_id=event.id,
            analysis_id=analysis.id,
            investor_id=investor.id,
            asset_id=asset.id,
            direction=direction,
            strength=70,
            confidence=0.8,
            thesis=["consistency thesis"],
            catalysts=[],
            risks=[],
            time_horizon=None,
            generated_time=analysis.generated_time,
            model_version=analysis_spec.model_version,
        )
        session.add(opinion)
        session.commit()
        opinion_id = opinion.id

    detection = PositionChangeDetectionService(lambda: SqlAlchemyPortfolioUnitOfWork(factory))
    detection_result = detection.detect(previous_batch.id, current_batch.id)
    assert detection_result.action_ids
    return investor.id, asset.id, opinion_id, detection_result.action_ids[0]


def _service(factory: sessionmaker[Session]) -> OpinionActionConsistencyService:
    return OpinionActionConsistencyService(
        lambda: SqlAlchemyConsistencyUnitOfWork(factory),
        POLICY,
    )


@pytest.mark.parametrize(
    ("direction", "previous_weight", "current_weight", "expected"),
    [
        (
            OpinionDirection.BULLISH,
            0.10,
            0.20,
            ConsistencyType.POSITIVE_ALIGNMENT,
        ),
        (
            OpinionDirection.BULLISH,
            0.20,
            0.10,
            ConsistencyType.NEGATIVE_ALIGNMENT,
        ),
        (
            OpinionDirection.BEARISH,
            0.20,
            0.10,
            ConsistencyType.POSITIVE_ALIGNMENT,
        ),
        (
            OpinionDirection.BEARISH,
            0.10,
            0.20,
            ConsistencyType.NEGATIVE_ALIGNMENT,
        ),
    ],
)
def test_direction_and_weight_changes_produce_deterministic_alignment(
    db_session_factory: sessionmaker[Session],
    direction: OpinionDirection,
    previous_weight: float,
    current_weight: float,
    expected: ConsistencyType,
) -> None:
    investor_id, asset_id, _, action_id = _seed_case(
        db_session_factory,
        direction=direction,
        previous_weight=previous_weight,
        current_weight=current_weight,
    )

    result = _service(db_session_factory).process(investor_id, asset_id)

    assert result.created_count == 1
    assert result.unmatched_action_ids == ()
    with db_session_factory() as session:
        artifact = session.get(InvestorActionConsistency, result.artifact_ids[0])
        assert artifact is not None
        assert artifact.portfolio_action_id == action_id
        assert artifact.consistency_type == expected.value
        assert artifact.opinion_analysis_version == ACTIVE_SPEC.analysis_version
        assert artifact.effective_time.replace(tzinfo=UTC) == CURRENT_TIME


def test_neutral_opinion_produces_no_direction(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id, _, _ = _seed_case(
        db_session_factory,
        direction=OpinionDirection.NEUTRAL,
        previous_weight=0.10,
        current_weight=0.20,
    )

    result = _service(db_session_factory).process(investor_id, asset_id)

    with db_session_factory() as session:
        artifact = session.get(InvestorActionConsistency, result.artifact_ids[0])
        assert artifact is not None
        assert artifact.consistency_type == ConsistencyType.NO_DIRECTION.value


@pytest.mark.parametrize(
    ("previous_weight", "current_weight"),
    [(None, 0.10), (0.10, None), (0.10, 0.10)],
)
def test_unsupported_or_non_changing_actions_do_not_claim_alignment(
    db_session_factory: sessionmaker[Session],
    previous_weight: float | None,
    current_weight: float | None,
) -> None:
    investor_id, asset_id, _, _ = _seed_case(
        db_session_factory,
        direction=OpinionDirection.BULLISH,
        previous_weight=previous_weight,
        current_weight=current_weight,
    )

    result = _service(db_session_factory).process(investor_id, asset_id)

    with db_session_factory() as session:
        artifact = session.get(InvestorActionConsistency, result.artifact_ids[0])
        assert artifact is not None
        assert artifact.consistency_type == ConsistencyType.INSUFFICIENT_EVIDENCE.value


def test_action_before_opinion_is_not_matched(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id, _, action_id = _seed_case(
        db_session_factory,
        direction=OpinionDirection.BULLISH,
        previous_weight=0.10,
        current_weight=0.20,
        opinion_time=CURRENT_TIME + timedelta(days=1),
    )

    result = _service(db_session_factory).process(investor_id, asset_id)

    assert result.artifact_ids == ()
    assert result.unmatched_action_ids == (action_id,)


def test_inactive_opinion_does_not_enter_consistency(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id, _, action_id = _seed_case(
        db_session_factory,
        direction=OpinionDirection.BULLISH,
        previous_weight=0.10,
        current_weight=0.20,
        analysis_spec=OLD_SPEC,
    )

    result = _service(db_session_factory).process(investor_id, asset_id)

    assert result.artifact_ids == ()
    assert result.unmatched_action_ids == (action_id,)
    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(InvestorActionConsistency)) == 0


def test_consistency_persistence_is_idempotent(
    db_session_factory: sessionmaker[Session],
) -> None:
    investor_id, asset_id, _, _ = _seed_case(
        db_session_factory,
        direction=OpinionDirection.BULLISH,
        previous_weight=0.10,
        current_weight=0.20,
    )
    service = _service(db_session_factory)

    first = service.process(investor_id, asset_id)
    second = service.process(investor_id, asset_id)

    assert first.created_count == 1
    assert first.reused_count == 0
    assert second.created_count == 0
    assert second.reused_count == 1
    assert first.artifact_ids == second.artifact_ids
    with db_session_factory() as session:
        repository = InvestorActionConsistencyRepository(session)
        assert len(repository.list_by_investor(investor_id)) == 1
        assert len(repository.list_by_asset(asset_id)) == 1
