"""Explicit zero-provider coordination of existing derived projections only."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select

from config import get_production_analysis_policy, get_production_thesis_comparison_policy
from contracts import IntelligenceEventType, IntelligencePriorityReason
from contracts.intelligence_feed import feed_display_context
from database.base import Base
from database.models import (
    Asset,
    CrossInvestorAssetAlignment,
    CrossInvestorConsensusEvidence,
    IntelligenceEventPriority,
    IntelligenceFeedItem,
    ThesisChange,
)
from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork
from intelligence.events.evidence import group_effective_thesis_evidence
from intelligence.feed.service import IntelligenceFeedService
from intelligence.priority.service import IntelligencePriorityService
from operations.locking import OperationalRefreshLock

TYPES = {
    IntelligenceEventType.INVESTOR_VIEW_CHANGE,
    IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
    IntelligenceEventType.CONSENSUS_STATE_CHANGE,
}


@contextmanager
def _refresh_lock(session):
    lock = OperationalRefreshLock(session)
    if not lock.try_acquire():
        raise ValueError("Concurrent canonical refresh; cannot apply")
    try:
        yield
    except BaseException:
        session.rollback()
        raise
    finally:
        lock.release()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _code_identity():
    root = Path(__file__).resolve().parents[1]

    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=root, stderr=subprocess.DEVNULL)

    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    return {
        "head": git("rev-parse", "HEAD").decode().strip(),
        "working_diff_sha256": hashlib.sha256(git("diff", "HEAD", "--binary")).hexdigest(),
        "coordinator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "untracked_code_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in untracked
            if Path(name).suffix in {".py", ".ts", ".tsx"}
        },
    }


def _scope(priority_id=None, asset_id=None, priority_ids=None):
    if sum(value is not None for value in (priority_id, asset_id, priority_ids)) != 1:
        raise ValueError("Exactly one explicit priority_id, asset_id or priority_ids is required")
    result = {
        "priority_id": str(priority_id) if priority_id else None,
        "asset_id": str(asset_id) if asset_id else None,
    }
    if priority_ids is not None:
        ids = tuple(UUID(str(value)) for value in priority_ids)
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("Explicit priority_ids must be nonempty and unique")
        result["priority_ids"] = sorted(str(value) for value in ids)
    return result


class _Memo:
    """Per preparation only: reuse established effective source readers."""

    def __init__(self, reader):
        self.reader = reader
        self.cache = {}

    def list(self):
        if "list" not in self.cache:
            self.cache["list"] = self.reader.list()
        return self.cache["list"]

    def group_by_events(self, events, links, signals):
        groups = self.cache.setdefault("events", {})
        missing = [event for event in events if event.id not in groups]
        if missing:
            loaded = self.reader.group_by_events(missing, links, signals)
            groups.update({event.id: loaded.get(event.id, ((), frozenset())) for event in missing})
        return {event.id: groups[event.id] for event in events}


class ProjectionReconciler:
    def __init__(self, session_factory):
        self.factory = session_factory

    def prepare(self, *, priority_id=None, asset_id=None, priority_ids=None):
        scope = _scope(priority_id, asset_id, priority_ids)
        with SqlAlchemyIntelligenceFeedUnitOfWork(self.factory) as uow:
            if uow._session.bind.dialect.name == "postgresql":
                uow._session.connection().exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
            return self._prepare(uow, **scope)

    def _prepare(self, uow, *, priority_id=None, asset_id=None, priority_ids=None):
        scope = _scope(priority_id, asset_id, priority_ids)
        priority_id = UUID(priority_id) if isinstance(priority_id, str) else priority_id
        asset_id = UUID(asset_id) if isinstance(asset_id, str) else asset_id
        requested = (
            {UUID(value) for value in scope["priority_ids"]} if priority_ids is not None else None
        )
        events = uow.intelligence_events.list()
        priorities = uow.intelligence_event_priorities.list()
        feeds = uow.intelligence_feed_items.list()
        links = uow.intelligence_event_evidence.list()
        signals = {s.id: s for s in uow.signals.list()}
        assets = set(uow._session.scalars(select(Asset.id)))
        source_ids = {
            name: set(uow._session.scalars(select(model.id)))
            for name, model in (
                ("ThesisChange", ThesisChange),
                ("CrossInvestorAssetAlignment", CrossInvestorAssetAlignment),
                ("CrossInvestorConsensusEvidence", CrossInvestorConsensusEvidence),
            )
        }
        event_map = {event.id: event for event in events}
        selected = (
            [p for p in priorities if p.id in requested]
            if requested is not None
            else (
                [p for p in priorities if p.id == priority_id]
                if priority_id
                else [
                    p
                    for p in priorities
                    if p.event_id in event_map and event_map[p.event_id].asset_id == asset_id
                ]
            )
        )
        selected.sort(key=lambda p: str(p.id))
        if not selected and requested is None:
            raise LookupError("No existing Priority in explicit scope")
        uow.effective_thesis_signals = _Memo(uow.effective_thesis_signals)
        uow.effective_cross_signals = _Memo(uow.effective_cross_signals)
        candidates = IntelligencePriorityService._candidates(
            uow, event_ids=[p.event_id for p in selected], reasons=None
        )
        by_event = {c.event_id: c for c in candidates}
        planned = {
            p.id: p.model_copy(
                update={
                    field: getattr(by_event[p.event_id], field)
                    for field in ("reason", "priority_level", "evidence_count")
                }
            )
            if p.event_id in by_event
            else p
            for p in priorities
        }
        reader = uow.intelligence_event_priorities
        uow.intelligence_event_priorities = SimpleNamespace(list=lambda: tuple(planned.values()))
        feed_candidates = {
            c.priority_id: c
            for c in IntelligenceFeedService._candidates(
                uow,
                priority_ids=[
                    p.id
                    for p in selected
                    if p.event_id in by_event and event_map[p.event_id].event_type in TYPES
                ],
            )
        }
        target_events = [
            event for event in events if event.id in by_event and event.event_type in TYPES
        ]
        thesis_events = [
            event
            for event in target_events
            if event.event_type is IntelligenceEventType.INVESTOR_VIEW_CHANGE
        ]
        groups = {}
        if thesis_events:
            groups.update(
                {
                    event_id: (values, frozenset(s.investor_id for s in values))
                    for event_id, values in group_effective_thesis_evidence(
                        thesis_events, links, uow.effective_thesis_signals.list()
                    ).items()
                }
            )
        cross_events = [
            event
            for event in target_events
            if event.event_type is not IntelligenceEventType.INVESTOR_VIEW_CHANGE
        ]
        if cross_events:
            groups.update(
                uow.effective_cross_signals.group_by_events(
                    cross_events, links, tuple(signals.values())
                )
            )
        items = []
        for missing in sorted((requested or set()) - {p.id for p in selected}, key=str):
            items.append(
                {
                    "priority_id": str(missing),
                    "event_id": None,
                    "asset_id": None,
                    "feed_ids": [],
                    "old_priority": None,
                    "old_feed": None,
                    "changes": {},
                    "status": "ANOMALY",
                    "error": "Missing requested Priority cannot be repaired",
                }
            )
        for priority in selected:
            event = event_map.get(priority.event_id)
            associated = [f for f in feeds if f.priority_id == priority.id]
            row = {
                "priority_id": str(priority.id),
                "event_id": str(priority.event_id),
                "asset_id": str(event.asset_id) if event else None,
                "feed_ids": [str(f.id) for f in associated],
                "old_priority": priority.model_dump(mode="json"),
                "old_feed": associated[0].model_dump(mode="json") if associated else None,
                "changes": {},
                "status": "ANOMALY",
            }
            row["dependencies"] = [
                {
                    "evidence_id": str(link.id),
                    "signal_id": str(link.signal_id),
                    "source_id": str(signals[link.signal_id].source_id)
                    if link.signal_id in signals
                    else None,
                    "source_type": signals[link.signal_id].source_type
                    if link.signal_id in signals
                    else None,
                }
                for link in links
                if link.event_id == priority.event_id
            ]
            effective, voters = groups.get(priority.event_id, ((), frozenset()))
            row["effective_evidence"] = [
                {
                    "signal_id": str(s.id),
                    "source_type": s.source_type,
                    "source_id": str(s.source_id),
                    "fact_observed_at": s.observed_at.isoformat(),
                    "investor_id": str(s.investor_id) if s.investor_id else None,
                }
                for s in effective
            ]
            row["effective_investor_ids"] = sorted(str(voter) for voter in voters)
            if event is None or event.event_type not in TYPES or len(associated) != 1:
                row["error"] = "Missing entity, unsupported Event type, or non-unique existing Feed"
            elif event.asset_id not in assets:
                row["error"] = "Missing Asset cannot be repaired"
            elif any(
                link.signal_id not in signals
                or signals[link.signal_id].source_id
                not in source_ids.get(signals[link.signal_id].source_type, set())
                for link in links
                if link.event_id == priority.event_id
            ):
                row["error"] = "Missing linked Signal or source cannot be repaired"
            elif (
                associated[0].asset_id != event.asset_id
                or associated[0].event_type != event.event_type
            ):
                row["error"] = "Feed identity mismatch cannot be repaired"
            elif priority.event_id not in by_event:
                row["status"] = "SKIPPED"
                row["error"] = (
                    "No eligible ACTIVE Event with effective evidence; preserve existing rows"
                )
            else:
                try:
                    candidate = feed_candidates[priority.id]
                    ep = {
                        f: planned[priority.id].model_dump(mode="json")[f]
                        for f in ("reason", "priority_level", "evidence_count")
                    }
                    ef = {
                        f: candidate.model_dump(mode="json")[f]
                        for f in ("reason", "title", "context", "observed_at")
                    }
                    row.update(expected_priority=ep, expected_feed=ef, status="READY")
                    for name, old, expected in (
                        ("priority", row["old_priority"], ep),
                        (
                            "feed",
                            {
                                **row["old_feed"],
                                "context": feed_display_context(associated[0].context),
                            },
                            ef,
                        ),
                    ):
                        for field, value in expected.items():
                            if old[field] != value:
                                row["changes"][name + "." + field] = {
                                    "old": old[field],
                                    "new": value,
                                }
                    if not row["changes"]:
                        row["status"] = "CONSISTENT"
                except (ValueError, LookupError) as error:
                    row["error"] = str(error)
            items.append(row)
        uow.intelligence_event_priorities = reader
        # Conservative guard reads all upstream rows to detect late/eligible inputs.
        # Unrelated changes can require a new plan, never expand its write scope.
        hashes = {}
        for table in Base.metadata.sorted_tables:
            if table.name in {"intelligence_event_priorities", "intelligence_feed_items"}:
                continue
            rows = [dict(row) for row in uow._session.execute(select(table)).mappings()]
            hashes[table.name] = _digest(sorted(_digest(row) for row in rows))
        policies = [
            str(get_production_analysis_policy()),
            str(get_production_thesis_comparison_policy()),
        ]
        items.sort(key=lambda item: item["priority_id"])
        identity = _code_identity()
        return {
            "schema": 2,
            "scope": scope,
            "code_identity": identity,
            "items": items,
            "source_guard": _digest([hashes, policies]),
            "fingerprint": _digest([scope, items, hashes, policies, identity]),
            "llm_calls": 0,
        }

    def apply(self, plan):
        with SqlAlchemyIntelligenceFeedUnitOfWork(self.factory) as uow:
            with _refresh_lock(uow._session):
                ids = [UUID(i["priority_id"]) for i in plan["items"]]
                uow._session.execute(
                    select(IntelligenceEventPriority)
                    .where(IntelligenceEventPriority.id.in_(ids))
                    .with_for_update()
                ).all()
                uow._session.execute(
                    select(IntelligenceFeedItem)
                    .where(IntelligenceFeedItem.priority_id.in_(ids))
                    .with_for_update()
                ).all()
                current = self._prepare(uow, **plan["scope"])
                if current != plan:
                    raise ValueError("stale projection plan; prepare again")
                if any(i["status"] == "ANOMALY" for i in current["items"]):
                    raise ValueError("Plan contains anomalies that cannot be repaired")
                ready = [i for i in current["items"] if i["status"] == "READY"]
                commands = IntelligencePriorityService._candidates(
                    uow, event_ids=[UUID(i["event_id"]) for i in ready], reasons=None
                )
                for command in commands:
                    writer = uow.intelligence_event_priorities
                    if command.reason is IntelligencePriorityReason.THESIS_CHANGE_OBSERVED:
                        writer.add_or_refresh_thesis_change(command)
                    else:
                        writer.add_or_refresh_cross_direction(command)
                for command in IntelligenceFeedService._candidates(
                    uow, priority_ids=[UUID(i["priority_id"]) for i in ready]
                ):
                    uow.intelligence_feed_items.add_if_absent(command)
                uow.commit()
        return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--priority-id", type=UUID)
    scope.add_argument("--asset-id", type=UUID)
    scope.add_argument(
        "--priority-ids-file", type=Path, help="JSON array of explicit Priority UUIDs"
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from database.session import SessionFactory

    service = ProjectionReconciler(SessionFactory)
    ids = (
        json.loads(args.priority_ids_file.read_text(encoding="utf8"))
        if args.priority_ids_file
        else None
    )
    if ids is not None and not isinstance(ids, list):
        raise ValueError("Whitelist file must be a JSON array")
    expected = _scope(args.priority_id, args.asset_id, ids)
    if args.apply:
        plan = json.loads(args.plan.read_text(encoding="utf8"))
        if plan["scope"] != expected:
            raise ValueError("Explicit scope does not match saved plan")
        result = service.apply(plan)
    else:
        result = service.prepare(
            priority_id=args.priority_id, asset_id=args.asset_id, priority_ids=ids
        )
        args.plan.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
