"""Conservative RawEvent checkpoints for Thesis-only stale reentry."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

from contracts import FeedItem
from contracts.intelligence_feed import THESIS_LIFECYCLE_CONTEXT_KEY, ThesisSourceFact


def read_baseline(feed: FeedItem, event_id: UUID) -> dict[str, object] | None:
    value = feed.context.get(THESIS_LIFECYCLE_CONTEXT_KEY)
    if value is None:
        return None
    try:
        if not isinstance(value, dict) or value["version"] != 1:
            raise ValueError()
        if value["event_id"] != str(event_id) or value["asset_id"] != str(feed.asset_id):
            raise ValueError()
        if not isinstance(value["known_raw_event_ids"], list) or not isinstance(
            value["consumed_facts"], dict
        ):
            raise ValueError()
        for identity in value["known_raw_event_ids"]:
            UUID(identity)
        for identity, timestamp in value["consumed_facts"].items():
            UUID(identity)
            parse_time(timestamp)
            if identity not in value["known_raw_event_ids"]:
                raise ValueError()
        if value["high_watermark"] is not None:
            parse_time(value["high_watermark"])
        if value.get("reentry_after") is not None:
            parse_time(value["reentry_after"])
        return deepcopy(value)
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError("Invalid Thesis lifecycle baseline; cannot reset progress") from exc


def parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("baseline time must be aware")
    return result.astimezone(UTC)


def baseline_progress(value: dict[str, object]) -> dict[str, object]:
    """Compare committed progress independently of diagnostic wall-clock fields."""
    return {
        key: item for key, item in value.items() if key not in {"initialized_at", "last_transition"}
    }


def checkpoint(
    feed: FeedItem,
    event_id: UUID,
    previous: dict[str, object] | None,
    facts: tuple[ThesisSourceFact, ...],
    known_ids: frozenset[UUID],
    now: datetime,
    transition: tuple[str, str, str] | None = None,
    supporting: tuple[ThesisSourceFact, ...] = (),
) -> dict[str, object]:
    result = (
        deepcopy(previous)
        if previous is not None
        else {
            "version": 1,
            "event_id": str(event_id),
            "asset_id": str(feed.asset_id),
            "known_raw_event_ids": [],
            "consumed_facts": {},
            "high_watermark": None,
            "initialized_at": now.isoformat(),
            "reentry_after": now.isoformat() if feed.state.value == "STALE" else None,
        }
    )
    result["known_raw_event_ids"] = sorted(
        set(result["known_raw_event_ids"]) | {str(item) for item in known_ids}
    )
    consumed = dict(result["consumed_facts"])
    for fact in facts:
        identity = str(fact.raw_event_id)
        if identity in consumed and parse_time(consumed[identity]) != fact.published_time:
            raise ValueError("RawEvent fact time differs from persisted Thesis baseline")
        consumed[identity] = fact.published_time.isoformat()
    result["consumed_facts"] = dict(sorted(consumed.items()))
    times = [fact.published_time for fact in facts if fact.published_time <= now]
    if result["high_watermark"] is not None:
        times.append(parse_time(result["high_watermark"]))
    result["high_watermark"] = max(times).isoformat() if times else None
    if feed.state.value == "STALE" and result.get("reentry_after") is None:
        result["reentry_after"] = now.isoformat()
    if transition:
        if transition[1] == "STALE":
            previous_floor = (
                parse_time(result["reentry_after"]) if result.get("reentry_after") else now
            )
            result["reentry_after"] = max(previous_floor, now).isoformat()
        result["last_transition"] = {
            "from_state": transition[0],
            "to_state": transition[1],
            "reason": transition[2],
            "evaluated_at": now.isoformat(),
            "source_facts": [
                {
                    "raw_event_id": str(f.raw_event_id),
                    "published_time": f.published_time.isoformat(),
                }
                for f in supporting
            ],
        }
    return result
