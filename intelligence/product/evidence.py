"""Read saved content behind accepted associations, never infer new intelligence."""

from datetime import UTC
from html.parser import HTMLParser
from urllib.parse import urlsplit

from sqlalchemy import select

from contracts import IntelligenceEventType, SignalState, SignalType
from contracts.raw_event import current_author_text
from database.models import (
    AttentionOccurrence,
    EventAnalysis,
    Investor,
    Opinion,
    RawEvent,
    ThesisChange,
)
from database.unit_of_work import SqlAlchemyAssetIntelligenceReadUnitOfWork
from intelligence.product.evidence_schemas import EvidenceReadingView
from intelligence.read_scope import AssetIntelligenceReadScopeLoader


class _BorrowedReadUnitOfWork(SqlAlchemyAssetIntelligenceReadUnitOfWork):
    """Outer content read owns the same rollback-only transaction as selection."""

    def __exit__(self, *_args):
        return None


class EvidenceUnavailable(ValueError):
    pass


def safe_source_url(value):
    try:
        parsed = urlsplit(value or "")
        if (
            parsed.scheme.lower() in {"http", "https"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not any(ord(c) <= 32 for c in value)
        ):
            return value
    except ValueError:
        pass
    return None


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class _ReadableText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.blocked = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.blocked += 1
        elif tag in {"p", "div", "br", "li"} and not self.blocked:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.blocked = max(0, self.blocked - 1)
        elif tag in {"p", "div", "li"} and not self.blocked:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)


def readable_text(content):
    # Preserve normal plain text exactly; HTML source remains separately available.
    if not any(
        f"<{tag}" in content.lower() for tag in ("p", "div", "br", "a", "span", "script", "img")
    ):
        return content
    reader = _ReadableText()
    reader.feed(content)
    return "".join(reader.parts).strip()


class EvidenceReadingService:
    def __init__(self, session_factory):
        self._factory = session_factory

    def read(
        self,
        asset_id,
        *,
        feed_id=None,
        signal_id=None,
        event_id=None,
        thesis_change_id=None,
        history=False,
    ):
        with self._factory() as session:
            try:
                return self._read(
                    session,
                    asset_id,
                    feed_id=feed_id,
                    signal_id=signal_id,
                    event_id=event_id,
                    thesis_change_id=thesis_change_id,
                    history=history,
                )
            finally:
                session.rollback()

    def _read(self, session, asset_id, *, feed_id, signal_id, event_id, thesis_change_id, history):
        if history and thesis_change_id is None:
            raise EvidenceUnavailable("历史上下文必须指定 ThesisChange，不能冒充当前情报。")
        if thesis_change_id and any((feed_id, signal_id, event_id)):
            raise EvidenceUnavailable("观点历史与情报关联范围不能混用。")
        scope = AssetIntelligenceReadScopeLoader(
            lambda: _BorrowedReadUnitOfWork(lambda: session), include_traceability=True
        ).load(asset_id)
        chains = list(scope.validated_source_chains or ())
        # Attention reading uses the existing effective Occurrence selector. It
        # exposes saved content only; it does not introduce a new Signal rule.
        occurrences = {a.id: a for a in scope.attention_occurrences}
        signals = scope.signals_by_id
        active_priorities = {f.priority_id for f in scope.feed_items if f.state.value == "ACTIVE"}
        active_events = {p.event_id for p in scope.priorities if p.id in active_priorities}
        events = {e.id: e for e in scope.events}
        for link in scope.historical_event_evidence or ():
            event, signal = events.get(link.event_id), signals.get(link.signal_id)
            if (
                not event
                or event.id not in active_events
                or event.event_type is not IntelligenceEventType.ASSET_ACTIVITY_SPIKE
            ):
                continue
            if (
                not signal
                or signal.state is not SignalState.ACTIVE
                or signal.signal_type is not SignalType.NEW_ATTENTION
                or signal.source_type != "AttentionOccurrence"
            ):
                continue
            occurrence = occurrences.get(signal.source_id)
            if (
                not occurrence
                or occurrence.asset_id != event.asset_id
                or signal.asset_id != event.asset_id
                or signal.investor_id != occurrence.investor_id
            ):
                continue
            chains.append(
                dict(
                    source_type="AttentionOccurrence",
                    source_id=occurrence.id,
                    signal_id=signal.id,
                    event_id=event.id,
                    observed_at=occurrence.published_time,
                    source_window_start=None,
                    source_window_end=None,
                    source_as_of=None,
                    direction_voter_ids=[],
                    attention_only_investor_ids=[occurrence.investor_id]
                    if not occurrence.opinion_id
                    else [],
                    opinion_facts=[dict(opinion_id=occurrence.opinion_id, role="ATTENTION_OPINION")]
                    if occurrence.opinion_id
                    else [],
                    attention_facts=[dict(attention_occurrence_id=occurrence.id)],
                )
            )
        if feed_id is not None:
            feed = next((f for f in scope.feed_items if f.id == feed_id), None)
            if feed is None or feed.state.value != "ACTIVE":
                raise EvidenceUnavailable("此情报已不具备当前有效来源或已离开 ACTIVE 状态。")
            priority = next((p for p in scope.priorities if p.id == feed.priority_id), None)
            if priority is None:
                raise ValueError(f"Priority missing for Feed: {feed.id}")
            if event_id is not None and event_id != priority.event_id:
                raise EvidenceUnavailable("Feed 与 Event 范围不一致。")
            event_id = priority.event_id
        if event_id is not None:
            chains = [c for c in chains if c["event_id"] == event_id]
        if signal_id is not None:
            chains = [c for c in chains if c["signal_id"] == signal_id]
        if any((feed_id, signal_id, event_id)) and not chains:
            raise EvidenceUnavailable("指定关联来源已失效或不在此情报内；未替换为其他证据。")
        changes = {}
        change_ids = {c["source_id"] for c in chains if c["source_type"] == "ThesisChange"}
        if thesis_change_id is not None:
            change_ids = {thesis_change_id}
            effective = {c.id for c in scope.thesis_changes}
            if not history and thesis_change_id not in effective:
                raise EvidenceUnavailable(
                    "该比较已不符合当前有效前驱或 policy；可单独读取历史上下文。"
                )
        if change_ids:
            changes = {
                c.id: c
                for c in session.scalars(
                    select(ThesisChange).where(ThesisChange.id.in_(change_ids))
                )
            }
        if change_ids - changes.keys():
            raise EvidenceUnavailable("比较来源不存在。")
        for c in changes.values():
            if c.asset_id != asset_id:
                raise EvidenceUnavailable("比较标的不一致。")
        if thesis_change_id is not None:
            c = changes[thesis_change_id]
            chains = [
                dict(
                    source_type="ThesisChange",
                    source_id=c.id,
                    event_id=None,
                    signal_id=None,
                    observed_at=_utc(c.effective_time),
                    opinion_facts=[
                        dict(opinion_id=oid, role=role)
                        for oid, role in [
                            (c.previous_opinion_id, "THESIS_PREVIOUS"),
                            (c.current_opinion_id, "THESIS_CURRENT"),
                        ]
                        if oid
                    ],
                    attention_facts=[],
                    direction_voter_ids=[],
                    attention_only_investor_ids=[],
                    source_window_start=None,
                    source_window_end=None,
                    source_as_of=None,
                )
            ]
        opinion_ids = {f["opinion_id"] for c in chains for f in c["opinion_facts"]}
        attention_ids = {f["attention_occurrence_id"] for c in chains for f in c["attention_facts"]}
        opinions = (
            {
                o.id: (o, raw, investor, analysis)
                for o, raw, investor, analysis in session.execute(
                    select(Opinion, RawEvent, Investor, EventAnalysis.analysis_version)
                    .join(RawEvent, Opinion.event_id == RawEvent.id)
                    .join(Investor, Opinion.investor_id == Investor.id)
                    .outerjoin(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
                    .where(Opinion.id.in_(opinion_ids))
                )
            }
            if opinion_ids
            else {}
        )
        attentions = (
            {
                a.id: (a, raw, investor)
                for a, raw, investor in session.execute(
                    select(AttentionOccurrence, RawEvent, Investor)
                    .join(RawEvent, AttentionOccurrence.event_id == RawEvent.id)
                    .join(Investor, AttentionOccurrence.investor_id == Investor.id)
                    .where(AttentionOccurrence.id.in_(attention_ids))
                )
            }
            if attention_ids
            else {}
        )
        if opinion_ids - opinions.keys() or attention_ids - attentions.keys():
            raise EvidenceUnavailable("原文或贡献者缺失，无法完整解析指定来源。")
        groups = []
        for chain in chains:
            c = changes.get(chain["source_id"])
            group = {
                key: chain.get(key)
                for key in (
                    "source_type",
                    "source_id",
                    "event_id",
                    "signal_id",
                    "observed_at",
                    "source_window_start",
                    "source_window_end",
                    "source_as_of",
                    "direction_voter_ids",
                    "attention_only_investor_ids",
                )
            }
            group["basis"] = (
                "HISTORICAL_REFERENCE"
                if history
                else "EFFECTIVE_HISTORY"
                if thesis_change_id
                else "CURRENT_ASSOCIATION"
            )
            group["comparison"] = (
                dict(
                    change_type=c.change_type.value,
                    summary=c.summary,
                    evidence=c.evidence,
                    confidence=c.confidence,
                    comparison_version=c.comparison_version,
                    opinion_analysis_version=c.opinion_analysis_version,
                )
                if c
                else None
            )
            group["opinions"] = []
            for fact in chain["opinion_facts"]:
                opinion, raw, investor, analysis = opinions[fact["opinion_id"]]
                if opinion.asset_id != asset_id or opinion.investor_id != raw.investor_id:
                    raise EvidenceUnavailable("观点与原文身份不一致。")
                if c is not None:
                    expected_event = (
                        c.previous_event_id
                        if fact["role"] == "THESIS_PREVIOUS"
                        else c.current_event_id
                    )
                    if raw.id != expected_event or opinion.investor_id != c.investor_id:
                        raise EvidenceUnavailable("比较前后来源身份不一致。")
                group["opinions"].append(
                    dict(
                        opinion_id=opinion.id,
                        role=fact["role"],
                        direction=opinion.direction.value,
                        thesis=opinion.thesis,
                        catalysts=opinion.catalysts,
                        risks=opinion.risks,
                        time_horizon=opinion.time_horizon,
                        confidence=opinion.confidence,
                        analysis_id=opinion.analysis_id,
                        model_version=opinion.model_version,
                        analysis_version=analysis,
                        raw=self._raw(raw, investor),
                    )
                )
            group["attention"] = []
            for fact in chain["attention_facts"]:
                attention, raw, investor = attentions[fact["attention_occurrence_id"]]
                if attention.asset_id != asset_id or attention.investor_id != raw.investor_id:
                    raise EvidenceUnavailable("关注贡献与原文身份不一致。")
                group["attention"].append(
                    dict(
                        attention_occurrence_id=attention.id,
                        attention_only=attention.investor_id
                        in chain["attention_only_investor_ids"],
                        raw=self._raw(raw, investor),
                    )
                )
            groups.append(group)
        return EvidenceReadingView(
            asset=dict(
                asset_id=asset_id,
                name=scope.asset.name,
                market=scope.asset.market,
                symbol=scope.asset.symbol,
            ),
            groups=groups,
            available_history=[
                dict(
                    thesis_change_id=c.id,
                    change_type=c.change_type.value,
                    effective_time=c.effective_time,
                    investor_id=c.investor_id,
                )
                for c in scope.thesis_changes
            ],
        )

    @staticmethod
    def _raw(raw, investor):
        author = current_author_text(raw.content, raw.raw_data)
        return dict(
            raw_event_id=raw.id,
            investor_id=investor.id,
            investor_name=investor.name,
            published_time=_utc(raw.published_time),
            source=raw.source,
            source_url=safe_source_url(raw.url),
            source_url_status=("AVAILABLE" if safe_source_url(raw.url) else "MISSING_OR_UNSAFE"),
            content=raw.content,
            readable_content=readable_text(raw.content),
            current_author_text=readable_text(author),
            contains_repost=raw.raw_data.get("post_kind") == "REPOST"
            or isinstance(raw.raw_data.get("retweeted_status"), dict),
        )
