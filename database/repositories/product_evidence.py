"""Resolve accepted Product associations to facts; no effective-selection algorithm."""

from datetime import UTC

from sqlalchemy import select

from contracts import SignalType
from database.models import AttentionOccurrence, EventAnalysis, Opinion, RawEvent, ThesisChange


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ProductEvidenceSourceReader:
    """Batch provenance for already selected, associated Thesis/direction Signals."""

    def __init__(self, session):
        self._session = session

    def resolve(self, asset_id, groups, snapshots, alignments, consensus):
        snapshots = {value.id: value for value in snapshots}
        alignments = {value.id: value for value in alignments}
        consensus = {value.id: value for value in consensus}
        thesis_ids = {
            signal.source_id
            for signals, _ in groups.values()
            for signal in signals
            if signal.signal_type is SignalType.THESIS_CHANGE
        }
        changes = (
            {
                row.id: row
                for row in self._session.scalars(
                    select(ThesisChange).where(ThesisChange.id.in_(thesis_ids))
                )
            }
            if thesis_ids
            else {}
        )
        specs = []
        opinion_ids, attention_ids = set(), set()
        for event_id, (signals, voters) in groups.items():
            for signal in signals:
                refs = {(signal.source_type, signal.source_id), ("Signal", signal.id)}
                roles, attention = [], []
                window = None
                if signal.signal_type is SignalType.THESIS_CHANGE:
                    change = changes.get(signal.source_id)
                    if change is None or change.asset_id != asset_id:
                        raise ValueError(f"Product Thesis source missing/mismatched: {signal.id}")
                    roles.append(
                        (
                            change.current_opinion_id,
                            change.investor_id,
                            change.current_event_id,
                            "THESIS_CURRENT",
                        )
                    )
                    if change.previous_opinion_id is not None:
                        roles.append(
                            (
                                change.previous_opinion_id,
                                change.investor_id,
                                change.previous_event_id,
                                "THESIS_PREVIOUS",
                            )
                        )
                else:
                    if signal.signal_type is SignalType.CONSENSUS_CHANGE:
                        source = consensus.get(signal.source_id)
                        if source is None:
                            raise ValueError(f"Product Consensus source missing: {signal.id}")
                        refs.add(("CrossInvestorAssetAlignment", source.source_alignment_id))
                        alignment = alignments.get(source.source_alignment_id)
                    else:
                        alignment = alignments.get(signal.source_id)
                        source = alignment
                    if alignment is None or source is None or source.asset_id != asset_id:
                        raise ValueError(
                            f"Product Alignment source missing/mismatched: {signal.id}"
                        )
                    snapshot = snapshots.get(alignment.source_snapshot_id)
                    if snapshot is None or snapshot.asset_id != asset_id:
                        raise ValueError(f"Product Snapshot source missing/mismatched: {signal.id}")
                    refs.add(("CrossInvestorAssetSnapshot", snapshot.id))
                    window = (snapshot.window_start, snapshot.window_end, snapshot.as_of)
                    for contribution in snapshot.contributions:
                        if contribution.window_opinion_count:
                            roles.append(
                                (
                                    contribution.latest_window_opinion_id,
                                    contribution.investor_id,
                                    None,
                                    "DIRECTION_VOTE",
                                )
                            )
                        attention.extend(
                            (identity, contribution.investor_id)
                            for identity in contribution.attention_occurrence_ids
                        )
                opinion_ids.update(identity for identity, *_ in roles)
                attention_ids.update(identity for identity, _ in attention)
                specs.append((event_id, signal, voters, refs, roles, attention, window))
        opinions = {}
        if opinion_ids:
            statement = (
                select(
                    Opinion.id,
                    Opinion.event_id,
                    Opinion.investor_id,
                    Opinion.asset_id,
                    RawEvent.published_time,
                    RawEvent.investor_id.label("raw_investor_id"),
                    EventAnalysis.event_id.label("analysis_event_id"),
                )
                .join(RawEvent, Opinion.event_id == RawEvent.id)
                .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
                .where(Opinion.id.in_(opinion_ids))
            )
            opinions = {row.id: row for row in self._session.execute(statement)}
        attentions = {}
        if attention_ids:
            statement = (
                select(
                    AttentionOccurrence.id,
                    AttentionOccurrence.event_id,
                    AttentionOccurrence.investor_id,
                    AttentionOccurrence.asset_id,
                    RawEvent.published_time,
                    RawEvent.investor_id.label("raw_investor_id"),
                )
                .join(RawEvent, AttentionOccurrence.event_id == RawEvent.id)
                .where(AttentionOccurrence.id.in_(attention_ids))
            )
            attentions = {row.id: row for row in self._session.execute(statement)}
        chains = []
        for event_id, signal, voters, refs, roles, attention, window in specs:
            facts, attention_facts = [], []
            for identity, investor, event_identity, role in roles:
                row = opinions.get(identity)
                if (
                    row is None
                    or row.asset_id != asset_id
                    or row.investor_id != investor
                    or (
                        row.raw_investor_id != investor
                        or row.analysis_event_id != row.event_id
                        or (event_identity is not None and event_identity != row.event_id)
                    )
                ):
                    raise ValueError(f"Product Opinion/RawEvent reference mismatch: {identity}")
                published = _utc(row.published_time)
                if role == "DIRECTION_VOTE" and not window[0] <= published <= window[1]:
                    raise ValueError(f"Product vote outside Snapshot window: {identity}")
                facts.append(
                    dict(
                        opinion_id=identity,
                        raw_event_id=row.event_id,
                        investor_id=investor,
                        published_time=published,
                        role=role,
                    )
                )
                refs.update({("Opinion", identity), ("RawEvent", row.event_id)})
            vote_ids = {f["investor_id"] for f in facts if f["role"] == "DIRECTION_VOTE"}
            if signal.signal_type is not SignalType.THESIS_CHANGE and not vote_ids <= voters:
                raise ValueError(f"Product vote identity mismatch: {signal.id}")
            for identity, investor in attention:
                row = attentions.get(identity)
                if (
                    row is None
                    or row.asset_id != asset_id
                    or row.investor_id != investor
                    or row.raw_investor_id != investor
                ):
                    raise ValueError(f"Product Attention/RawEvent reference mismatch: {identity}")
                attention_facts.append(
                    dict(
                        attention_occurrence_id=identity,
                        raw_event_id=row.event_id,
                        investor_id=investor,
                        published_time=_utc(row.published_time),
                    )
                )
                refs.update({("AttentionOccurrence", identity), ("RawEvent", row.event_id)})
            participants = (
                vote_ids
                if signal.signal_type is not SignalType.THESIS_CHANGE
                else {signal.investor_id}
            )
            chains.append(
                dict(
                    event_id=event_id,
                    signal_id=signal.id,
                    source_type=signal.source_type,
                    source_id=signal.source_id,
                    observed_at=signal.observed_at,
                    source_window_start=window[0] if window else None,
                    source_window_end=window[1] if window else None,
                    source_as_of=window[2] if window else None,
                    investor_ids=tuple(sorted(participants, key=str)),
                    direction_voter_ids=tuple(sorted(vote_ids, key=str)),
                    attention_only_investor_ids=tuple(
                        sorted({f["investor_id"] for f in attention_facts} - vote_ids, key=str)
                    ),
                    opinion_facts=tuple(facts),
                    attention_facts=tuple(attention_facts),
                    evidence_refs=tuple(
                        dict(source_type=kind, source_id=identity)
                        for kind, identity in sorted(refs, key=lambda x: (x[0], str(x[1])))
                    ),
                )
            )
        return tuple(
            sorted(chains, key=lambda chain: (str(chain["event_id"]), str(chain["signal_id"])))
        )
