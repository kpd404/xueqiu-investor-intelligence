"""Small user-owned workflow. All intelligence remains selected by existing readers."""

import hashlib
import json
from datetime import UTC
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from database.models import (
    Asset,
    AttentionOccurrence,
    EventAnalysis,
    IntelligenceEventPriority,
    IntelligenceFeedItem,
    Investor,
    Opinion,
    RawEvent,
    ResearchCandidate,
)
from database.models._types import utc_now
from intelligence.product.evidence import EvidenceReadingService, EvidenceUnavailable


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID | None = None
    signal_id: UUID | None = None
    thesis_change_id: UUID | None = None

    @model_validator(mode="after")
    def exact_selection(self):
        if self.thesis_change_id is not None:
            if self.event_id is not None or self.signal_id is not None:
                raise ValueError("不能混合观点历史与情报来源身份。")
        elif self.event_id is None or self.signal_id is None:
            raise ValueError("必须同时指定实际 Event 和 Signal。")
        return self


class AddResearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: UUID
    submission_id: UUID
    feed_id: UUID | None = None
    selections: list[Selection] = Field(min_length=1, max_length=100)
    reason: str = Field(default="", max_length=20000)
    questions: str = Field(default="", max_length=20000)
    notes: str = Field(default="", max_length=50000)


class EditResearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=20000)
    questions: str | None = Field(default=None, max_length=20000)
    notes: str | None = Field(default=None, max_length=50000)
    status: Literal["TODO", "RESEARCHING", "ARCHIVED"] | None = None


def reference_key(ref):
    return (ref["event_id"], ref["signal_id"], ref["source_type"], ref["source_id"])


class ResearchService:
    def __init__(self, session_factory, evidence_factory=None):
        self.sessions = session_factory
        self.evidence_factory = evidence_factory or session_factory

    def add(self, request: AddResearch):
        with self.sessions() as session:
            if session.get_bind().dialect.name == "postgresql":
                session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            # PostgreSQL locks per asset; partial index also guards open identity.
            if (
                session.scalar(select(Asset).where(Asset.id == request.asset_id).with_for_update())
                is None
            ):
                raise LookupError("标的不存在。")
            existing = session.scalars(
                select(ResearchCandidate).where(ResearchCandidate.asset_id == request.asset_id)
            ).all()
            submission = str(request.submission_id)
            fingerprint = hashlib.sha256(
                json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()
            ).hexdigest()
            replay = next(
                (r for r in existing if any(v["id"] == submission for v in r.submission_ids)), None
            )
            if replay:
                previous = next(v for v in replay.submission_ids if v["id"] == submission)
                if previous["fingerprint"] != fingerprint:
                    raise ValueError("相同提交身份的内容不同，请准备新的提交。")
                return self._view(session, replay)
            # Validate all selections once, in the same transaction as the user-only write.
            reader = EvidenceReadingService(lambda: session)
            view = reader._read(
                session,
                request.asset_id,
                feed_id=request.feed_id,
                signal_id=None,
                event_id=None,
                thesis_change_id=None,
                history=False,
            )
            # Persist actual Feed provenance even when entered from Product.
            feed_by_event = {
                event_id: feed_id
                for event_id, feed_id in session.execute(
                    select(IntelligenceEventPriority.event_id, IntelligenceFeedItem.id)
                    .join(
                        IntelligenceFeedItem,
                        IntelligenceFeedItem.priority_id == IntelligenceEventPriority.id,
                    )
                    .where(
                        IntelligenceEventPriority.event_id.in_(
                            {g.event_id for g in view.groups if g.event_id is not None}
                        ),
                        IntelligenceFeedItem.asset_id == request.asset_id,
                        IntelligenceFeedItem.state == "ACTIVE",
                    )
                )
            }
            selected = []
            for choice in request.selections:
                matches = [
                    g
                    for g in view.groups
                    if (
                        choice.signal_id is not None
                        and g.signal_id == choice.signal_id
                        and choice.event_id is not None
                        and g.event_id == choice.event_id
                    )
                    or (
                        choice.thesis_change_id is not None
                        and g.source_type == "ThesisChange"
                        and g.source_id == choice.thesis_change_id
                    )
                ]
                if not matches and choice.thesis_change_id is not None and request.feed_id is None:
                    matches = list(
                        reader._read(
                            session,
                            request.asset_id,
                            feed_id=None,
                            signal_id=None,
                            event_id=None,
                            thesis_change_id=choice.thesis_change_id,
                            history=False,
                        ).groups
                    )
                if len(matches) != 1:
                    raise EvidenceUnavailable("所选证据与标的/情报不匹配，或当前已失效。")
                g = matches[0]
                selected.append(
                    {
                        "feed_id": str(request.feed_id or feed_by_event[g.event_id])
                        if g.event_id is not None
                        else None,
                        "event_id": str(g.event_id) if g.event_id else None,
                        "signal_id": str(g.signal_id) if g.signal_id else None,
                        "source_type": g.source_type,
                        "source_id": str(g.source_id),
                        "observed_at": g.observed_at.isoformat(),
                        "opinion_ids": [str(o.opinion_id) for o in g.opinions],
                        "raw_event_ids": sorted(
                            {str(o.raw.raw_event_id) for o in g.opinions}
                            | {str(a.raw.raw_event_id) for a in g.attention}
                        ),
                        "saved_group": g.model_dump(mode="json", exclude={"opinions", "attention"}),
                        "opinion_roles": {str(o.opinion_id): o.role for o in g.opinions},
                        "attention_ids": [str(a.attention_occurrence_id) for a in g.attention],
                    }
                )
            candidate = next((r for r in existing if r.status != "ARCHIVED"), None)
            if candidate is None:
                candidate = ResearchCandidate(
                    asset_id=request.asset_id,
                    reason=request.reason,
                    questions=request.questions,
                    notes=request.notes,
                    references=[],
                    submission_ids=[],
                )
                session.add(candidate)
            merged = {reference_key(r): r for r in candidate.references}
            previous_count = len(merged)
            for ref in selected:
                merged.setdefault(reference_key(ref), ref)
            candidate.references = list(merged.values())
            candidate.submission_ids = [
                *candidate.submission_ids,
                {"id": submission, "fingerprint": fingerprint},
            ]
            if len(merged) != previous_count:
                candidate.updated_at = utc_now()
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("同标的候选被并发修改，请重新提交。") from exc
            return self._view(session, candidate)

    def edit(self, candidate_id, request: EditResearch):
        with self.sessions() as session:
            candidate = session.get(ResearchCandidate, candidate_id)
            if candidate is None:
                raise LookupError("研究候选不存在。")
            session.scalar(select(Asset).where(Asset.id == candidate.asset_id).with_for_update())
            for field, value in request.model_dump(exclude_unset=True).items():
                if value is None:
                    raise ValueError("字段不能为 null。")
                setattr(candidate, field, value)
            candidate.updated_at = utc_now()
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("同标的已有未归档候选，不能恢复为重复记录。") from exc
            return self._view(session, candidate)

    def list(self):
        with self.sessions() as session:
            rows = session.scalars(
                select(ResearchCandidate).order_by(
                    ResearchCandidate.created_at.desc(), ResearchCandidate.id
                )
            ).all()
            return {"items": [self._view(session, r) for r in rows]}

    def read(self, candidate_id):
        with self.sessions() as session:
            candidate = session.get(ResearchCandidate, candidate_id)
            if candidate is None:
                raise LookupError("研究候选不存在。")
            result = self._view(session, candidate)
        result["sources"] = [
            self._source(UUID(result["asset_id"]), ref) for ref in result["references"]
        ]
        return result

    @staticmethod
    def _view(session, row):
        asset = session.get(Asset, row.asset_id)
        return {
            "id": str(row.id),
            "asset_id": str(row.asset_id),
            "asset_name": asset.name,
            "status": row.status,
            "reason": row.reason,
            "questions": row.questions,
            "notes": row.notes,
            "references": row.references,
            "created_at": row.created_at.replace(tzinfo=UTC).isoformat()
            if row.created_at.tzinfo is None
            else row.created_at.isoformat(),
            "updated_at": row.updated_at.replace(tzinfo=UTC).isoformat()
            if row.updated_at.tzinfo is None
            else row.updated_at.isoformat(),
        }

    def _source(self, asset_id, ref):
        reader = EvidenceReadingService(self.evidence_factory)
        params = dict(
            feed_id=UUID(ref["feed_id"]) if ref["feed_id"] else None,
            event_id=UUID(ref["event_id"]) if ref["event_id"] else None,
            signal_id=UUID(ref["signal_id"]) if ref["signal_id"] else None,
            thesis_change_id=UUID(ref["source_id"]) if not ref["signal_id"] else None,
        )
        try:
            view = reader.read(asset_id, **params)
            if not any(
                set(ref["opinion_ids"]) == {str(o.opinion_id) for o in g.opinions}
                and ref["source_id"] == str(g.source_id)
                for g in view.groups
            ):
                raise EvidenceUnavailable("保存的具体引用已不代表当前有效来源。")
            return {
                "status": "CURRENT",
                "message": "本次查询来源仍有效；不代表投资结论。",
                "evidence": view.model_dump(mode="json"),
            }
        except (EvidenceUnavailable, ValueError, LookupError) as exc:
            # Retain exact saved identities; never swap in an unrelated current source.
            with self.evidence_factory() as session:
                rows = session.execute(
                    select(Opinion, RawEvent, Investor, EventAnalysis.analysis_version)
                    .join(RawEvent, Opinion.event_id == RawEvent.id)
                    .join(Investor, Investor.id == Opinion.investor_id)
                    .outerjoin(EventAnalysis, EventAnalysis.id == Opinion.analysis_id)
                    .where(
                        Opinion.id.in_([UUID(i) for i in ref["opinion_ids"]]),
                        Opinion.asset_id == asset_id,
                    )
                ).all()
                if len(rows) != len(ref["opinion_ids"]):
                    return {
                        "status": "UNAVAILABLE",
                        "message": "保存的来源实体缺失；用户记录保留。",
                        "evidence": None,
                    }
                group = dict(
                    ref["saved_group"], basis="HISTORICAL_REFERENCE", attention=[], opinions=[]
                )
                for opinion, raw, investor, version in rows:
                    if (
                        str(raw.id) not in ref["raw_event_ids"]
                        or raw.investor_id != opinion.investor_id
                    ):
                        return {
                            "status": "UNAVAILABLE",
                            "message": "保存的来源身份异常。",
                            "evidence": None,
                        }
                    group["opinions"].append(
                        dict(
                            opinion_id=str(opinion.id),
                            role=ref["opinion_roles"][str(opinion.id)],
                            direction=opinion.direction.value,
                            thesis=opinion.thesis,
                            catalysts=opinion.catalysts,
                            risks=opinion.risks,
                            time_horizon=opinion.time_horizon,
                            confidence=opinion.confidence,
                            analysis_id=str(opinion.analysis_id) if opinion.analysis_id else None,
                            analysis_version=version,
                            model_version=opinion.model_version,
                            raw=reader._raw(raw, investor),
                        )
                    )
                attention_rows = session.execute(
                    select(AttentionOccurrence, RawEvent, Investor)
                    .join(RawEvent, AttentionOccurrence.event_id == RawEvent.id)
                    .join(Investor, Investor.id == AttentionOccurrence.investor_id)
                    .where(
                        AttentionOccurrence.id.in_([UUID(i) for i in ref.get("attention_ids", [])]),
                        AttentionOccurrence.asset_id == asset_id,
                    )
                ).all()
                if len(attention_rows) != len(ref.get("attention_ids", [])):
                    return {
                        "status": "UNAVAILABLE",
                        "message": "保存的关注来源缺失。",
                        "evidence": None,
                    }
                for attention, raw, investor in attention_rows:
                    if (
                        str(raw.id) not in ref["raw_event_ids"]
                        or raw.investor_id != attention.investor_id
                    ):
                        return {
                            "status": "UNAVAILABLE",
                            "message": "保存的关注身份异常。",
                            "evidence": None,
                        }
                    group["attention"].append(
                        dict(
                            attention_occurrence_id=str(attention.id),
                            attention_only=str(investor.id) in group["attention_only_investor_ids"],
                            raw=reader._raw(raw, investor),
                        )
                    )
                asset = session.get(Asset, asset_id)
                return {
                    "status": "HISTORICAL"
                    if isinstance(exc, EvidenceUnavailable)
                    else "UNVERIFIED",
                    "message": str(exc) + " 保存引用仅作为历史上下文。",
                    "evidence": {
                        "asset": {
                            "asset_id": str(asset.id),
                            "name": asset.name,
                            "market": asset.market,
                            "symbol": asset.symbol,
                        },
                        "groups": [group],
                        "available_history": [],
                        "historical_completeness": "UNKNOWN",
                    },
                }
