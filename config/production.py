"""Explicit production analysis policy source.

Provider runtime defaults are intentionally separate from the interpretation
policy approved for normal downstream consumption. A provider/model change
must be accompanied by an explicit production-version update.
"""

from config.common import Settings, get_settings
from contracts import (
    OPINION_ANALYSIS_POLICY_VERSION,
    OPINION_EXTRACTION_PROMPT_VERSION,
    OPINION_EXTRACTION_SCHEMA_VERSION,
    THESIS_COMPARISON_POLICY_VERSION,
    THESIS_COMPARISON_PROMPT_VERSION,
    THESIS_COMPARISON_SCHEMA_VERSION,
    AnalysisSpec,
    AnalysisType,
    EffectiveAnalysisPolicy,
    ProductionAnalysisPolicy,
)


class ProductionPolicyConfigurationError(ValueError):
    """Raised when runtime provider settings do not match the approved policy."""


def get_production_policy(
    analysis_type: AnalysisType,
    settings: Settings | None = None,
) -> ProductionAnalysisPolicy:
    """Return one explicitly approved production analysis policy.

    The approved analysis version is a configuration value. It is checked
    against the semantic identity derived from the configured provider/model,
    rather than being silently replaced by provider defaults.
    """

    resolved = settings or get_settings()
    provider_id = resolved.llm_provider_id
    model = resolved.llm_model
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ProductionPolicyConfigurationError("LLM_PROVIDER_ID is not configured")
    if not isinstance(model, str) or not model.strip():
        raise ProductionPolicyConfigurationError("LLM_MODEL is not configured")

    if analysis_type is AnalysisType.OPINION_EXTRACTION:
        prompt_version = OPINION_EXTRACTION_PROMPT_VERSION
        schema_version = OPINION_EXTRACTION_SCHEMA_VERSION
        analysis_policy_version = OPINION_ANALYSIS_POLICY_VERSION
        approved = resolved.production_opinion_analysis_version.strip()
    elif analysis_type is AnalysisType.THESIS_COMPARISON:
        prompt_version = THESIS_COMPARISON_PROMPT_VERSION
        schema_version = THESIS_COMPARISON_SCHEMA_VERSION
        analysis_policy_version = THESIS_COMPARISON_POLICY_VERSION
        approved = resolved.production_thesis_comparison_version.strip()
    else:
        raise ProductionPolicyConfigurationError(
            f"unsupported production analysis type: {analysis_type}"
        )

    candidate = AnalysisSpec.for_provider(
        provider_id=provider_id,
        model_version=model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        analysis_policy_version=analysis_policy_version,
    )
    if candidate.analysis_version != approved:
        raise ProductionPolicyConfigurationError(
            "configured provider/model does not match the approved production analysis version"
        )
    return ProductionAnalysisPolicy(analysis_type=analysis_type, active_spec=candidate)


def get_production_analysis_policy(
    settings: Settings | None = None,
) -> ProductionAnalysisPolicy:
    """Return the approved Opinion Extraction policy."""

    return get_production_policy(AnalysisType.OPINION_EXTRACTION, settings)


def get_production_thesis_comparison_policy(
    settings: Settings | None = None,
) -> ProductionAnalysisPolicy:
    """Return the approved Thesis Comparison policy."""

    return get_production_policy(AnalysisType.THESIS_COMPARISON, settings)


def get_production_effective_policy(
    settings: Settings | None = None,
) -> EffectiveAnalysisPolicy:
    """Adapt the single production policy source to existing service ports."""

    return get_production_analysis_policy(settings).as_effective_policy()
