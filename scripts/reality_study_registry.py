"""Immutable candidate manifest for the next Investor Reality Study.

This is an operational, read-only registry. It is intentionally not a
database model and has no persistence or status-update side effect. The
registry prepares human verification before any historical collection starts.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

REALITY_STUDY_TARGET_ROUND = "2F.3.3-R1-14"


class RealityStudyCandidateStatus(StrEnum):
    """Control-plane status for a candidate, not an intelligence state."""

    PENDING_HUMAN_VERIFICATION = "PENDING_HUMAN_VERIFICATION"
    READY_FOR_BACKFILL = "READY_FOR_BACKFILL"
    BACKFILL_IN_PROGRESS = "BACKFILL_IN_PROGRESS"
    COMPLETED = "COMPLETED"
    HOLD = "HOLD"


class RealityStudyCandidate(BaseModel):
    """One immutable candidate record used by the human verification step."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    investor_id: UUID
    xueqiu_user_id: str = Field(min_length=1)
    priority_reason: str = Field(min_length=1, max_length=1000)
    target_round: str = Field(min_length=1, max_length=100)
    status: RealityStudyCandidateStatus


class RealityStudyCandidateRegistry(BaseModel):
    """Validated immutable collection of Reality Study candidates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[RealityStudyCandidate, ...] = ()

    @model_validator(mode="after")
    def validate_unique_identity(self) -> RealityStudyCandidateRegistry:
        investor_ids = [candidate.investor_id for candidate in self.candidates]
        xueqiu_user_ids = [candidate.xueqiu_user_id for candidate in self.candidates]
        if len(set(investor_ids)) != len(investor_ids):
            raise ValueError("reality study candidates must have unique investor_id values")
        if len(set(xueqiu_user_ids)) != len(xueqiu_user_ids):
            raise ValueError("reality study candidates must have unique xueqiu_user_id values")
        return self

    def by_investor_id(self, investor_id: UUID) -> RealityStudyCandidate | None:
        return next(
            (candidate for candidate in self.candidates if candidate.investor_id == investor_id),
            None,
        )

    def by_xueqiu_user_id(self, xueqiu_user_id: str) -> RealityStudyCandidate | None:
        normalized = xueqiu_user_id.strip()
        return next(
            (candidate for candidate in self.candidates if candidate.xueqiu_user_id == normalized),
            None,
        )


DEFAULT_REALITY_STUDY_CANDIDATE_REGISTRY = RealityStudyCandidateRegistry(
    candidates=(
        RealityStudyCandidate(
            investor_id=UUID("25b92042-f642-46d8-b1b1-780293dffa0d"),
            xueqiu_user_id="9086045991",
            priority_reason=(
                "Highest effective Opinion depth and broadest Asset coverage; connects nine "
                "existing overlap Assets, including two 3-Investor overlaps."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("1ec47ea5-2d15-4538-9b60-6e7d330c7391"),
            xueqiu_user_id="4364582897",
            priority_reason=(
                "Nineteen effective Opinions with repeated history and four shared Assets; "
                "covers two 3-Investor overlaps."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("33e2013b-78fe-4379-a0b1-a4fbf354fd69"),
            xueqiu_user_id="1344684945",
            priority_reason=(
                "All five observed Assets already overlap another Investor; provides a compact "
                "but comparatively dense longitudinal evidence set."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("7b1847e6-9eaf-464b-9f5a-a7cce8a3ee60"),
            xueqiu_user_id="8799248060",
            priority_reason=(
                "Three shared Assets and multi-day Attention, with a large unresolved evidence "
                "gap that may fill 中远海控、山西焦煤 and 特变电工 overlap coverage."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("f4667372-75b6-41a1-8691-b546eb2180c1"),
            xueqiu_user_id="1107378837",
            priority_reason=(
                "Three effective Opinions from three successful analyses, no unresolved entries, "
                "and one clean overlap on 龙源电力."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("3eb8af09-ee15-4347-a884-0c0ad6b9fd7c"),
            xueqiu_user_id="7448680761",
            priority_reason=(
                "High information density across three distinct Assets; retained as a clean "
                "unique-coverage control despite no current overlap."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("b7e97331-2502-4e08-a16c-3c9acb0dfe95"),
            xueqiu_user_id="6007161345",
            priority_reason=(
                "Acts as an overlap connector for 盐湖股份、西部矿业 and 特变电工, with "
                "cross-day Attention evidence."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("1e9a511a-9f45-4da5-a0d3-8494019a4d37"),
            xueqiu_user_id="7103876041",
            priority_reason=(
                "Both effective Opinions focus on 华能国际, the current 3-Investor overlap where "
                "the other two Investors lack effective Opinion evidence."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("c2d0352b-9783-47fb-bab6-33b4c6f69ffd"),
            xueqiu_user_id="9957341637",
            priority_reason=(
                "Provides the second Investor on 盐湖股份 and a useful Neutral-versus-Bullish "
                "directional comparison with 周周小盈Peter投资."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("400b2a9f-ce0a-492f-9caf-e3c34dea189f"),
            xueqiu_user_id="1910783512",
            priority_reason=(
                "Touches three overlap Assets, including two 3-Investor overlaps; selected to "
                "investigate a high-volume but currently sparse Opinion evidence gap."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("6b91353c-b3ef-4e85-a00a-a1feb7be78e7"),
            xueqiu_user_id="7807171102",
            priority_reason=(
                "Provides a bearish index-view control on 上证指数 alongside 人生是历练, "
                "despite the small sample."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("b28cce38-8595-4631-9bea-bf145802e2f4"),
            xueqiu_user_id="6238316110",
            priority_reason=(
                "Retains one effective Opinion on the unique index Asset 深证成指 as a low-volume "
                "independent control."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
        ),
        RealityStudyCandidate(
            investor_id=UUID("684a134e-32af-4bae-aec4-33bb476f02fd"),
            xueqiu_user_id="5681120951",
            priority_reason=(
                "Only one effective Attention Asset and no effective Opinion; kept as a low-"
                "evidence recovery candidate, not a core priority."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.HOLD,
        ),
        RealityStudyCandidate(
            investor_id=UUID("73db7e50-2565-4c06-bc0b-6b84f6cb39fe"),
            xueqiu_user_id="3216879181",
            priority_reason=(
                "Twelve RawEvents but no effective Opinion or Attention; retained only as a "
                "verification control until evidence quality is confirmed."
            ),
            target_round=REALITY_STUDY_TARGET_ROUND,
            status=RealityStudyCandidateStatus.HOLD,
        ),
    )
)


def get_reality_study_candidate_registry() -> RealityStudyCandidateRegistry:
    """Return the immutable default registry without reading or writing storage."""

    return DEFAULT_REALITY_STUDY_CANDIDATE_REGISTRY
