"""Read-only PostgreSQL calibration for Thesis Evolution V0."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.engine import URL, make_url

from config import get_production_analysis_policy, get_settings
from database.models.asset import Asset
from database.models.investor import Investor
from database.models.raw_event import RawEvent
from database.session import SessionFactory
from database.unit_of_work import SqlAlchemyObservedAttentionUnitOfWork
from intelligence.services.thesis_evolution import ThesisEvolutionService

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


def _identity_maps() -> tuple[dict[str, UUID], dict[tuple[str, str], UUID]]:
    with _read_only_session() as session:
        investors = {
            name: investor_id
            for investor_id, name in session.execute(select(Investor.id, Investor.name))
        }
        assets = {
            (market, symbol): asset_id
            for asset_id, market, symbol in session.execute(
                select(Asset.id, Asset.market, Asset.symbol)
            )
        }
    return investors, assets


def _label(timeline: Any) -> str:
    return f"{timeline.investor_name} × {timeline.asset_name} {timeline.market}:{timeline.symbol}"


def _entry_label(entry: Any) -> str:
    direction = entry.direction.value
    semantic = entry.thesis_change_type.value if entry.thesis_change_type else "—"
    status = entry.thesis_comparison_status.value
    return f"{direction}/{semantic}/{status}"


def _print_top(title: str, timelines: list[Any], key) -> None:
    print(title)
    for timeline in sorted(
        timelines,
        key=lambda value: (-key(value), _label(value)),
    )[:10]:
        print(
            f"- {_label(timeline)}: value={key(timeline)} "
            f"opinions={timeline.opinion_count} changes={timeline.thesis_change_count}"
        )
    print()


def _run() -> int:
    settings = get_settings()
    url: URL = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            "Thesis Evolution V0 calibration requires PostgreSQL; "
            f"configured backend is {url.get_backend_name()}"
        )

    window_start, window_end = _window()
    investors, assets = _identity_maps()

    def uow_factory() -> SqlAlchemyObservedAttentionUnitOfWork:
        return SqlAlchemyObservedAttentionUnitOfWork(_read_only_session)

    service = ThesisEvolutionService.from_production(uow_factory)
    timelines = list(
        service.list_thesis_timelines(
            window_start,
            window_end,
            min_opinions=1,
            include_attention_context=True,
        )
    )
    repeated = [timeline for timeline in timelines if timeline.opinion_count >= 2]
    entries = [entry for timeline in timelines for entry in timeline.entries]
    change_types = Counter(
        entry.thesis_change_type.value for entry in entries if entry.thesis_change_type is not None
    )
    transitions = Counter(entry.direction_transition.value for entry in entries)
    missing_entries = [
        entry
        for entry in entries
        if entry.thesis_comparison_status.value == "MISSING_THESIS_COMPARISON"
    ]
    reversal_timelines = [timeline for timeline in timelines if timeline.reversal_count > 0]
    reversal_events = sum(timeline.reversal_count for timeline in timelines)
    same_direction_changed = sum(
        entry.thesis_change_type.value == "THESIS_CHANGED"
        and entry.direction_transition.value == "SAME_DIRECTION"
        for entry in entries
        if entry.thesis_change_type is not None
    )
    same_direction_extended = sum(
        entry.thesis_change_type.value == "THESIS_EXTENDED"
        and entry.direction_transition.value == "SAME_DIRECTION"
        for entry in entries
        if entry.thesis_change_type is not None
    )

    print("# Thesis Evolution V0 PostgreSQL Calibration")
    print()
    print(f"Database: {url.database}")
    print(f"Window: {_fmt_time(window_start)} -> {_fmt_time(window_end)}")
    print(
        f"Production Analysis identity: {get_production_analysis_policy().active_analysis_version}"
    )
    print(f"Thesis comparison version: {settings.production_thesis_comparison_version}")
    print("Completeness: UNKNOWN (current observed sequence only)")
    print(f"Timelines total: {len(timelines)}")
    print(f"Repeated timelines (Opinion count >= 2): {len(repeated)}")
    print(f"Opinion rows represented: {len(entries)}")
    print(
        f"ThesisChange rows attached: {sum(timeline.thesis_change_count for timeline in timelines)}"
    )
    print(f"Missing Thesis comparison entries: {len(missing_entries)}")
    print()

    print(
        "Opinion count distribution: "
        + ", ".join(
            f"{count}={quantity}"
            for count, quantity in sorted(
                Counter(timeline.opinion_count for timeline in timelines).items()
            )
        )
    )
    print(
        "ThesisChange type distribution: "
        + ", ".join(
            f"{change_type}={change_types.get(change_type, 0)}"
            for change_type in (
                "NEW_THESIS",
                "THESIS_REINFORCED",
                "THESIS_EXTENDED",
                "THESIS_CHANGED",
                "THESIS_UNCHANGED",
                "INSUFFICIENT_EVIDENCE",
            )
        )
    )
    print(
        "Direction transition distribution: "
        + ", ".join(
            f"{transition}={transitions.get(transition, 0)}"
            for transition in (
                "INITIAL_DIRECTION",
                "SAME_DIRECTION",
                "BULLISH_TO_BEARISH",
                "BEARISH_TO_BULLISH",
                "TO_NEUTRAL",
                "FROM_NEUTRAL",
                "OTHER",
            )
        )
    )
    print(f"Reversal timelines: {len(reversal_timelines)}")
    print(f"Reversal events: {reversal_events}")
    print(f"Same-direction THESIS_CHANGED: {same_direction_changed}")
    print(f"Same-direction THESIS_EXTENDED: {same_direction_extended}")
    print()

    _print_top("## Top timelines by Opinion count", timelines, lambda value: value.opinion_count)
    _print_top(
        "## Top timelines by THESIS_CHANGED count", timelines, lambda value: value.changed_count
    )
    _print_top("## Top timelines by reversal count", timelines, lambda value: value.reversal_count)
    _print_top(
        "## Top timelines by THESIS_EXTENDED count", timelines, lambda value: value.extended_count
    )

    print("## Representative real-data regressions")
    cases = (
        ("爱投资的小人书", "HK", "00902"),
        ("人生是历练", "HK", "01818"),
        ("人生是历练", "HK", "01787"),
        ("沈阳城", "HK", "02099"),
        ("爱投资的小人书", "HK", "00991"),
    )
    case_timelines: dict[tuple[str, str, str], Any] = {}
    for investor_name, market, symbol in cases:
        investor_id = investors.get(investor_name)
        asset_id = assets.get((market, symbol))
        if investor_id is None or asset_id is None:
            raise AssertionError(f"missing regression identity: {investor_name} {market}:{symbol}")
        timeline = service.get_thesis_timeline(
            investor_id,
            asset_id,
            window_start,
            window_end,
            include_attention_context=True,
        )
        if timeline is None:
            raise AssertionError(f"missing regression timeline: {investor_name} {market}:{symbol}")
        case_timelines[(investor_name, market, symbol)] = timeline
        print(
            f"- {_label(timeline)} | opinions={timeline.opinion_count} "
            f"changes={timeline.thesis_change_count} "
            f"missing={timeline.missing_thesis_change_count} "
            f"reversals={timeline.reversal_count}"
        )
        print("  " + " | ".join(_entry_label(entry) for entry in timeline.entries))

    expected_counts = {
        ("爱投资的小人书", "HK", "00902"): (16, 16, 0),
        ("人生是历练", "HK", "01818"): (13, 13, 0),
        ("人生是历练", "HK", "01787"): (12, 12, 0),
        ("沈阳城", "HK", "02099"): (8, 8, 0),
        ("爱投资的小人书", "HK", "00991"): (14, 13, 1),
    }
    for case, expected in expected_counts.items():
        timeline = case_timelines[case]
        actual = (
            timeline.opinion_count,
            timeline.thesis_change_count,
            timeline.missing_thesis_change_count,
        )
        if actual != expected:
            raise AssertionError(f"{case} expected {expected}, got {actual}")
    print("- PASS: representative Opinion/Thesis counts match the current reality baseline")
    print("- PASS: HK:01787 and HK:00991 remain listing-scoped by Asset id")
    print()

    print("## Missing comparison detail")
    for timeline in timelines:
        for entry in timeline.entries:
            if entry.thesis_comparison_status.value == "MISSING_THESIS_COMPARISON":
                print(
                    f"- {_label(timeline)} | Opinion={entry.opinion_id} "
                    f"RawEvent={entry.raw_event_id} predecessor={entry.predecessor_opinion_id}"
                )
    print()
    print("No score, ranking, persisted timeline, or LLM call was used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
