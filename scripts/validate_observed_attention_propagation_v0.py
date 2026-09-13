"""Read-only PostgreSQL calibration for Observed Attention Propagation V0."""

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
from intelligence.services.observed_attention_propagation import (
    ObservedAttentionPropagationService,
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


def _hk(value: datetime) -> datetime:
    return _utc(value).astimezone(HK)


def _fmt_time(value: datetime) -> str:
    return _hk(value).isoformat(timespec="seconds")


def _fmt_observation(observation: Any) -> str:
    evidence = "+".join(item.value for item in observation.evidence_types)
    direction = (
        observation.first_opinion_direction.value
        if observation.first_opinion_direction is not None
        else "—"
    )
    return (
        f"{observation.investor_name} @ {_fmt_time(observation.published_time)} "
        f"[{evidence}; Opinion={direction}; "
        f"AttentionOccurrence={observation.attention_occurrence_id}; "
        f"RawEvent={observation.raw_event_id}]"
    )


def _bucket(lag_days: float) -> str:
    if lag_days <= 1:
        return "<=1d"
    if lag_days <= 3:
        return "1-3d"
    if lag_days <= 7:
        return "3-7d"
    return ">7d"


def _asset_label(sequence: Any) -> str:
    return f"{sequence.asset_name} {sequence.market}:{sequence.symbol}"


def _get_window() -> tuple[datetime, datetime]:
    with _read_only_session() as session:
        start, end = session.execute(
            select(func.min(RawEvent.published_time), func.max(RawEvent.published_time))
        ).one()
        session.rollback()
    if start is None or end is None:
        raise RuntimeError("raw_events has no published_time range")
    return _utc(start), _utc(end)


def _find_sequence(sequences: tuple[Any, ...], market: str, symbol: str) -> Any:
    matches = [item for item in sequences if item.market == market and item.symbol == symbol]
    if len(matches) != 1:
        raise AssertionError(f"expected one sequence for {market}:{symbol}, got {len(matches)}")
    return matches[0]


def _run() -> int:
    settings = get_settings()
    url: URL = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            "Observed Attention Propagation V0 calibration requires PostgreSQL; "
            f"configured backend is {url.get_backend_name()}"
        )

    window_start, window_end = _get_window()

    def uow_factory() -> SqlAlchemyObservedAttentionUnitOfWork:
        return SqlAlchemyObservedAttentionUnitOfWork(_read_only_session)

    service = ObservedAttentionPropagationService.from_production(uow_factory)
    sequences = service.get_observed_attention_sequences(
        window_start,
        window_end,
        min_investors=2,
        include_thesis_context=True,
    )
    edges = tuple(
        edge
        for sequence in sequences
        for edge in ObservedAttentionPropagationService.derive_edges(sequence)
    )

    print("# Observed Attention Propagation V0 PostgreSQL Calibration")
    print()
    print(f"Database: {url.database}")
    print(f"Window: {_fmt_time(window_start)} -> {_fmt_time(window_end)}")
    print(
        f"Production Analysis identity: {get_production_analysis_policy().active_analysis_version}"
    )
    print("Attention policy: attention-occurrence-v1")
    print("Completeness: UNKNOWN (monitored-sample presence only)")
    print(f"Shared Attention Assets / sequences: {len(sequences)}")
    print(f"Generated anchor-to-later edges: {len(edges)}")
    print()

    print("## Generated sequences")
    for sequence in sequences:
        observations = (sequence.first_observed, *sequence.later_observations)
        span = (
            _utc(observations[-1].published_time) - _utc(observations[0].published_time)
        ).total_seconds() / 86400
        print(
            f"- {_asset_label(sequence)} | investors={sequence.investor_count} "
            f"occurrences={sequence.occurrence_count} span={span:.2f}d"
        )
        for index, observation in enumerate(observations):
            prefix = "first" if index == 0 else f"later+{observation.lag_days:.2f}d"
            print(f"  - {prefix}: {_fmt_observation(observation)}")
    print()

    lag_counts = Counter(_bucket(edge.lag_days) for edge in edges)
    relation_counts = Counter(edge.direction_relation.value for edge in edges)
    temporal_counts = Counter(edge.temporal_relation.value for edge in edges)
    print("## Calibration distributions")
    print(
        "Lag buckets: "
        + ", ".join(
            f"{bucket}={lag_counts.get(bucket, 0)}" for bucket in ("<=1d", "1-3d", "3-7d", ">7d")
        )
    )
    print(
        "Direction relation: "
        + ", ".join(
            f"{relation}={relation_counts.get(relation, 0)}"
            for relation in (
                "SAME_DIRECTION",
                "OPPOSITE_DIRECTION",
                "NEUTRAL_OR_MIXED",
                "OPINION_MISSING",
            )
        )
    )
    print(
        "Temporal relation: "
        + ", ".join(
            f"{relation}={temporal_counts.get(relation, 0)}"
            for relation in ("OBSERVED_LATER", "SIMULTANEOUS_OBSERVATION")
        )
    )
    print()

    print("## Top Assets by Investor count")
    for sequence in sorted(
        sequences,
        key=lambda item: (-item.investor_count, -item.occurrence_count, _asset_label(item)),
    )[:10]:
        print(f"- {_asset_label(sequence)}: {sequence.investor_count}")
    print()

    print("## Top Assets by temporal span")
    by_span = sorted(
        sequences,
        key=lambda item: (
            -(
                _utc(item.later_observations[-1].published_time)
                - _utc(item.first_observed.published_time)
            ).total_seconds(),
            _asset_label(item),
        ),
    )
    for sequence in by_span[:10]:
        span_days = (
            _utc(sequence.later_observations[-1].published_time)
            - _utc(sequence.first_observed.published_time)
        ).total_seconds() / 86400
        print(f"- {_asset_label(sequence)}: {span_days:.2f}d")
    print()

    print("## Representative regression cases")
    for market, symbol in (
        ("SH", "601872"),
        ("HK", "00916"),
        ("SH", "600519"),
        ("SH", "600547"),
        ("HK", "01787"),
    ):
        sequence = _find_sequence(sequences, market, symbol)
        names = [sequence.first_observed.investor_name] + [
            item.investor_name for item in sequence.later_observations
        ]
        opinion_breadth = len(
            {
                item.investor_id
                for item in (sequence.first_observed, *sequence.later_observations)
                if item.first_effective_opinion_id is not None
            }
        )
        print(
            f"- {_asset_label(sequence)}: {' -> '.join(names)}; "
            f"attention_investors={sequence.investor_count}; opinion_investors={opinion_breadth}"
        )
    sh = _find_sequence(sequences, "SH", "600547")
    hk = _find_sequence(sequences, "HK", "01787")
    if sh.asset_id == hk.asset_id:
        raise AssertionError("listing separation regression failed for 山东黄金")
    print("- 山东黄金 listing separation: SH:600547 and HK:01787 have distinct Asset ids")

    print()
    print("## Regression assertions")
    expected招商轮船 = ["笨笨的投资者2", "沈阳城", "Captain-Nemo船长", "看好股市的新人"]
    actual招商轮船 = [
        _find_sequence(sequences, "SH", "601872").first_observed.investor_name,
        *[
            item.investor_name
            for item in _find_sequence(sequences, "SH", "601872").later_observations
        ],
    ]
    if actual招商轮船 != expected招商轮船:
        raise AssertionError(f"招商轮船 order mismatch: {actual招商轮船}")
    龙源 = _find_sequence(sequences, "HK", "00916")
    actual龙源 = [龙源.first_observed.investor_name] + [
        item.investor_name for item in 龙源.later_observations
    ]
    if actual龙源 != ["沈阳城", "重组专家", "爱投资的小人书"]:
        raise AssertionError(f"龙源电力 order mismatch: {actual龙源}")
    茅台 = _find_sequence(sequences, "SH", "600519")
    茅台_opinion_breadth = len(
        {
            item.investor_id
            for item in (茅台.first_observed, *茅台.later_observations)
            if item.first_effective_opinion_id is not None
        }
    )
    if not 茅台.investor_count > 茅台_opinion_breadth:
        raise AssertionError("贵州茅台 should have wider Attention than Opinion breadth")
    print("- PASS: sequence ordering and listing separation")
    print(
        "- PASS: direction relation, provenance, completeness, and thesis context are query-derived"
    )
    print("- PASS: no persistence, score, ranking, causality, or absence field is generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
