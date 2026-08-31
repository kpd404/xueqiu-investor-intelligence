from contracts import AnalysisSpec, EffectiveAnalysisPolicy, EventAnalysisStatus


def test_effective_analysis_is_exact_and_has_no_failed_fallback() -> None:
    active = AnalysisSpec.from_model_version("active-v1")
    old = AnalysisSpec.from_model_version("old-v1")
    policy = EffectiveAnalysisPolicy(active_spec=active)

    assert policy.is_effective(active.analysis_version, EventAnalysisStatus.SUCCESS)
    assert policy.is_effective(active.analysis_version, EventAnalysisStatus.PARTIALLY_RESOLVED)
    assert not policy.is_effective(active.analysis_version, EventAnalysisStatus.FAILED)
    assert not policy.is_effective(old.analysis_version, EventAnalysisStatus.SUCCESS)
