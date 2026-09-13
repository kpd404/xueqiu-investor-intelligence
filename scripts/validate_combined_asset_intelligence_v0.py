"""Read-only PostgreSQL calibration for Combined Asset Intelligence View V0."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.engine import URL, make_url

from config import get_production_analysis_policy, get_settings
from database.models.raw_event import RawEvent
from database.session import SessionFactory
from database.unit_of_work import SqlAlchemyObservedAttentionUnitOfWork
from intelligence.services.combined_asset_intelligence import (
    CombinedAssetIntelligenceService,
)

HK = timezone(timedelta(hours=8), name="Asia/Hong_Kong")


def _read_only_session():
    session = SessionFactory()
    try:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        session.execute(text("SET LOCAL TIME ZONE 'Asia/Hong_Kong'"))
        session.execute(text("SET LOCAL statement_timeout = '60000'"))
    except Exception:
        session.close()
        raise
    return session


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _fmt_time(value: datetime) -> str:
    return _utc(value).astimezone(HK).isoformat(timespec="seconds")


def _window() -> tuple[datetime, datetime]:
    with _read_only_session() as session:
        start, end = session.execute(
            select(func.min(RawEvent.published_time), func.max(RawEvent.published_time))
        ).one()
    if start is None or end is None:
        raise RuntimeError("raw_events has no published_time range")
    return _utc(start), _utc(end)


def _label(view: Any) -> str:
    return f"{view.asset_name} {view.market}:{view.symbol}"


def _event_label(event: Any) -> str:
    direction = event.direction.value if event.direction is not None else "—"
    thesis = event.thesis_change_type.value if event.thesis_change_type is not None else "—"
    evidence = "+".join(item.value for item in event.evidence_types) or "—"
    return (
        f"{_fmt_time(event.published_time)} | {event.investor_name} | "
        f"{event.event_type.value} | {evidence} | direction={direction} | thesis={thesis}"
    )


def _investor_count(view: Any) -> int:
    return sum(item.opinion_count > 0 for item in view.investor_views)


def _representative_views(views: list[Any]) -> list[Any]:
    preferred = (
        ("SH", "601872"),
        ("HK", "00916"),
        ("SH", "600519"),
        ("HK", "00902"),
        ("HK", "00991"),
        ("HK", "01787"),
        ("SH", "600547"),
    )
    by_listing = {(view.market, view.symbol): view for view in views}
    selected = [by_listing[key] for key in preferred if key in by_listing]
    remaining = [
        view for view in sorted(views, key=lambda item: _label(item)) if view not in selected
    ]
    return (selected + remaining)[:7]


def _run() -> int:
    settings = get_settings()
    url: URL = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            "Combined View calibration requires PostgreSQL; "
            f"configured backend is {url.get_backend_name()}"
        )

    window_start, window_end = _window()

    def uow_factory() -> SqlAlchemyObservedAttentionUnitOfWork:
        return SqlAlchemyObservedAttentionUnitOfWork(_read_only_session)

    service = CombinedAssetIntelligenceService.from_production(uow_factory)
    views = list(service.list_asset_views(window_start, window_end))
    investor_views = [item for view in views for item in view.investor_views]
    relation_counts = Counter(item.attention_opinion_relation.value for item in investor_views)
    disagreement_alignment = sum(
        view.alignment is not None
        and view.alignment.directional_alignment_state.value == "MIXED_DIRECTION"
        for view in views
    )
    disagreement_consensus = sum(
        view.consensus is not None and view.consensus.consensus_state.value == "DIVERGENT"
        for view in views
    )
    repeated_thesis_views = sum(
        any(
            item.opinion_count >= 2 and item.thesis_change_count > 0 for item in view.investor_views
        )
        for view in views
    )
    repeated_thesis_pairs = sum(
        item.opinion_count >= 2 and item.thesis_change_count > 0 for item in investor_views
    )
    missing_views = [
        view for view in views if view.data_quality.missing_thesis_comparison_count > 0
    ]
    missing_pairs = sum(item.missing_thesis_comparison_count > 0 for item in investor_views)
    shared_views = [view for view in views if view.attention_summary.attention_investor_count >= 2]
    multi_opinion_views = [view for view in views if _investor_count(view) >= 2]
    alignment_views = [view for view in views if view.alignment is not None]
    consensus_views = [view for view in views if view.consensus is not None]
    sequence_edge_count = sum(len(view.attention_summary.temporal_edges) for view in views)
    simultaneous_edges = sum(
        edge.temporal_relation.value == "SIMULTANEOUS_OBSERVATION"
        for view in views
        for edge in view.attention_summary.temporal_edges
    )

    print("# Combined Asset Intelligence View V0 PostgreSQL Calibration")
    print()
    print(f"Database: {url.database}")
    print(f"Window: {_fmt_time(window_start)} -> {_fmt_time(window_end)}")
    print(
        f"Production Analysis identity: {get_production_analysis_policy().active_analysis_version}"
    )
    print("Completeness: UNKNOWN (current observed evidence only)")
    print(f"Combined Views total: {len(views)}")
    print(f"Shared Attention Views (2+ Investors): {len(shared_views)}")
    print(f"Multi-Opinion Views (2+ Opinion Investors): {len(multi_opinion_views)}")
    print(f"Views with existing active Alignment: {len(alignment_views)}")
    print(f"Views with existing active Consensus: {len(consensus_views)}")
    print(f"Observed Attention temporal edges: {sequence_edge_count}")
    print()
    print(
        "Attention-without-Opinion Investor×Asset: "
        f"{relation_counts.get('ATTENTION_WITHOUT_OPINION', 0)}"
    )
    print(
        "Opinion-after-Attention Investor×Asset: "
        f"{relation_counts.get('OPINION_AFTER_ATTENTION', 0)}"
    )
    print(
        "Opinion-at-first-Attention Investor×Asset: "
        f"{relation_counts.get('OPINION_AT_FIRST_ATTENTION', 0)}"
    )
    print(
        "Opinion-without-prior-Attention Investor×Asset: "
        f"{relation_counts.get('OPINION_WITHOUT_PRIOR_ATTENTION', 0)}"
    )
    print(f"Simultaneous Investor×Asset relations: {relation_counts.get('SIMULTANEOUS', 0)}")
    print(f"Simultaneous Attention temporal edges: {simultaneous_edges}")
    print(f"Views with Alignment MIXED_DIRECTION: {disagreement_alignment}")
    print(f"Views with Consensus DIVERGENT: {disagreement_consensus}")
    print(f"Views with repeated Thesis evolution: {repeated_thesis_views}")
    print(f"Investor×Asset pairs with repeated Thesis evolution: {repeated_thesis_pairs}")
    print(f"Views with missing Thesis comparison: {len(missing_views)}")
    print(f"Investor×Asset pairs with missing Thesis comparison: {missing_pairs}")
    print()

    print("## Representative product timelines")
    for view in _representative_views(views):
        opinion_investors = _investor_count(view)
        consensus = view.consensus.consensus_state.value if view.consensus else "—"
        print(
            f"- {_label(view)} | Attention={view.attention_summary.attention_investor_count} "
            f"investors/{view.attention_summary.attention_occurrence_count} occurrences | "
            f"Opinion={opinion_investors} investors | Consensus={consensus} | "
            f"missing_thesis={view.data_quality.missing_thesis_comparison_count}"
        )
        for event in view.event_timeline:
            print(f"  - {_event_label(event)}")
    print()
    print("No new semantic, score, ranking, Signal, persistence, or LLM call was used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
