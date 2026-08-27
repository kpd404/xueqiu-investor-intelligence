from contracts import AnalysisSpec, LLMProviderConfig

BASE = {
    "provider_id": "provider-a",
    "model_version": "same-model",
    "prompt_version": "opinion-extraction-v1",
    "schema_version": "opinion-extraction-result-v2",
}


def spec(**updates: str) -> AnalysisSpec:
    return AnalysisSpec.for_provider(**{**BASE, **updates})


def test_same_semantic_provider_configuration_has_stable_identity() -> None:
    first = spec()
    second = spec()

    assert first == second
    assert first.analysis_version == second.analysis_version
    assert first.identity_payload == {
        "analysis_policy_version": "opinion-analysis-v2",
        "model": "same-model",
        "prompt_version": "opinion-extraction-v1",
        "provider_id": "provider-a",
        "schema_version": "opinion-extraction-result-v2",
    }


def test_provider_model_prompt_schema_and_policy_each_change_identity() -> None:
    baseline = spec()
    variants = (
        spec(provider_id="provider-b"),
        spec(model_version="different-model"),
        spec(prompt_version="opinion-extraction-v2"),
        spec(schema_version="opinion-extraction-result-v3"),
        spec(analysis_policy_version="opinion-analysis-v3"),
    )
    assert all(candidate.analysis_version != baseline.analysis_version for candidate in variants)


def test_runtime_credentials_timeout_and_retry_are_not_identity_fields() -> None:
    first_config = LLMProviderConfig(
        provider_id="provider-a",
        base_url="https://gateway.example.test/v1",
        api_key="key-a",
        model="same-model",
        timeout_seconds=10,
        max_retries=0,
    )
    second_config = first_config.model_copy(
        update={"api_key": "key-b", "timeout_seconds": 120, "max_retries": 5}
    )

    first = spec(provider_id=first_config.provider_id, model_version=first_config.model)
    second = spec(provider_id=second_config.provider_id, model_version=second_config.model)

    assert first.analysis_version == second.analysis_version
