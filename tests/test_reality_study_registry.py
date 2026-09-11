from uuid import UUID

import pytest
from pydantic import ValidationError

from scripts.reality_study_registry import (
    DEFAULT_REALITY_STUDY_CANDIDATE_REGISTRY,
    RealityStudyCandidate,
    RealityStudyCandidateRegistry,
    RealityStudyCandidateStatus,
    get_reality_study_candidate_registry,
)


def test_default_registry_is_the_14_investor_read_only_manifest() -> None:
    registry = get_reality_study_candidate_registry()

    assert registry is DEFAULT_REALITY_STUDY_CANDIDATE_REGISTRY
    assert len(registry.candidates) == 14
    assert len({candidate.investor_id for candidate in registry.candidates}) == 14
    assert len({candidate.xueqiu_user_id for candidate in registry.candidates}) == 14
    assert all(candidate.target_round == "2F.3.3-R1-14" for candidate in registry.candidates)


def test_candidate_and_registry_are_immutable() -> None:
    candidate = get_reality_study_candidate_registry().candidates[0]

    with pytest.raises(ValidationError):
        candidate.status = RealityStudyCandidateStatus.COMPLETED  # type: ignore[misc]

    with pytest.raises(TypeError):
        get_reality_study_candidate_registry().candidates[0] = candidate  # type: ignore[index]


def test_registry_rejects_duplicate_identity() -> None:
    candidate = RealityStudyCandidate(
        investor_id=UUID("00000000-0000-0000-0000-000000000001"),
        xueqiu_user_id="100",
        priority_reason="test",
        target_round="test",
        status=RealityStudyCandidateStatus.HOLD,
    )

    with pytest.raises(ValidationError, match="unique investor_id"):
        RealityStudyCandidateRegistry(candidates=(candidate, candidate))


def test_registry_supports_identity_lookup() -> None:
    registry = get_reality_study_candidate_registry()
    candidate = registry.candidates[0]

    assert registry.by_investor_id(candidate.investor_id) == candidate
    assert registry.by_xueqiu_user_id(candidate.xueqiu_user_id) == candidate
    assert registry.by_xueqiu_user_id("missing") is None
