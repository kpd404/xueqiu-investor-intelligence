from datetime import UTC, datetime
from uuid import uuid4

import pytest

from config import (
    ProductionPolicyConfigurationError,
    Settings,
    get_production_analysis_policy,
    get_production_attention_policy_version,
)
from contracts import (
    OPINION_ANALYSIS_POLICY_VERSION,
    OPINION_EXTRACTION_PROMPT_VERSION,
    OPINION_EXTRACTION_SCHEMA_VERSION,
    PRODUCTION_OPINION_ANALYSIS_VERSION,
    AnalysisType,
    ProcessRawEventCommand,
)


def _settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "llm_provider_id": "volcengine-ark-coding",
        "llm_base_url": "https://gateway.example.test/v1",
        "llm_api_key": "test-key",
        "llm_model": "deepseek-v4-flash",
        "production_opinion_analysis_version": PRODUCTION_OPINION_ANALYSIS_VERSION,
    }
    values.update(updates)
    return Settings(**values)


def test_production_policy_is_explicit_and_adapts_to_effective_policy() -> None:
    policy = get_production_analysis_policy(_settings())

    assert policy.analysis_type is AnalysisType.OPINION_EXTRACTION
    assert policy.active_analysis_version == PRODUCTION_OPINION_ANALYSIS_VERSION
    assert policy.active_spec.provider_id == "volcengine-ark-coding"
    assert policy.active_spec.model_version == "deepseek-v4-flash"
    assert policy.active_spec.prompt_version == OPINION_EXTRACTION_PROMPT_VERSION
    assert policy.active_spec.schema_version == OPINION_EXTRACTION_SCHEMA_VERSION
    assert policy.active_spec.analysis_policy_version == OPINION_ANALYSIS_POLICY_VERSION
    assert policy.as_effective_policy().active_analysis_version == policy.active_analysis_version
    command = ProcessRawEventCommand.for_production(
        event_id=uuid4(),
        as_of=datetime(2026, 9, 3, tzinfo=UTC),
        policy=policy,
    )
    assert command.analysis_spec == policy.active_spec
    assert get_production_attention_policy_version() == "attention-occurrence-v1"


@pytest.mark.parametrize(
    "updates",
    [
        {"llm_provider_id": "different-provider"},
        {"llm_model": "different-model"},
        {"production_opinion_analysis_version": "opinion-analysis-v2:old"},
    ],
)
def test_provider_defaults_cannot_silently_change_production_policy(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ProductionPolicyConfigurationError):
        get_production_analysis_policy(_settings(**updates))
