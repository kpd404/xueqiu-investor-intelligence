import ast
import importlib
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def imported_roots(relative_path: str) -> set[str]:
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.partition(".")[0])

    return roots


def package_modules(package: str, *, exclude: set[str] | None = None) -> list[str]:
    excluded = exclude or set()
    root = PROJECT_ROOT / package
    return [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sorted(root.rglob("*.py"))
        if path.relative_to(PROJECT_ROOT).as_posix() not in excluded
    ]


def assert_package_boundary(
    package: str, forbidden: set[str], *, exclude: set[str] | None = None
) -> None:
    violations = {
        module: sorted(imported_roots(module) & forbidden)
        for module in package_modules(package, exclude=exclude)
        if imported_roots(module) & forbidden
    }
    assert violations == {}


def test_common_config_has_no_layer_dependencies() -> None:
    forbidden = {"backend", "database", "collector", "collectors"}
    assert imported_roots("config/common.py").isdisjoint(forbidden)


@pytest.mark.parametrize(
    "database_module",
    ["database/session.py", "database/migrations/env.py"],
)
def test_database_configuration_does_not_depend_on_backend(database_module: str) -> None:
    imports = imported_roots(database_module)
    assert "config" in imports
    assert "backend" not in imports


@pytest.mark.parametrize(
    "package_name",
    [
        "ai",
        "collectors",
        "config",
        "contracts",
        "intelligence",
        "ingestion",
        "pipeline",
        "resolution",
        "signal_engine",
    ],
)
def test_layer_package_is_importable(package_name: str) -> None:
    assert importlib.import_module(package_name)


def test_signal_engine_does_not_shadow_python_standard_library() -> None:
    standard_library_signal = importlib.import_module("signal")

    assert hasattr(standard_library_signal, "Signals")
    assert importlib.import_module("signal_engine")


def test_pyproject_discovers_layer_packages() -> None:
    import tomllib

    configuration: dict[str, Any] = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    includes = set(configuration["tool"]["setuptools"]["packages"]["find"]["include"])

    assert {
        "ai*",
        "backend*",
        "collectors*",
        "config*",
        "contracts*",
        "database*",
        "intelligence*",
        "ingestion*",
        "pipeline*",
        "resolution*",
        "prompts*",
        "signal_engine*",
    } <= includes


@pytest.mark.parametrize(
    "adapter_module",
    ["collectors/base.py", "collectors/manual/adapter.py"],
)
def test_collector_adapters_do_not_depend_on_persistence_or_ai(adapter_module: str) -> None:
    imports = imported_roots(adapter_module)
    assert imports.isdisjoint({"ai", "database", "sqlalchemy"})


def test_xueqiu_adapter_does_not_cross_service_boundaries() -> None:
    imports = imported_roots("collectors/xueqiu/adapter.py")
    assert imports.isdisjoint(
        {"ai", "database", "intelligence", "signal", "signal_engine", "sqlalchemy"}
    )


def test_feed_ingestion_is_the_persistence_application_boundary() -> None:
    imports = imported_roots("ingestion/following_feed.py")
    assert {"database", "sqlalchemy"} <= imports
    assert imports.isdisjoint({"ai", "intelligence", "signal", "signal_engine"})


def test_asset_resolver_is_source_and_persistence_independent() -> None:
    imports = imported_roots("resolution/asset_resolver.py")
    assert imports.isdisjoint({"ai", "collectors", "database", "sqlalchemy"})


def test_asset_recovery_is_source_and_provider_independent() -> None:
    imports = imported_roots("resolution/recovery.py")
    assert imports.isdisjoint({"ai", "collectors", "database", "sqlalchemy"})


def test_attention_matcher_is_pure_and_source_independent() -> None:
    imports = imported_roots("intelligence/policies/mention_matcher.py")
    assert imports.isdisjoint(
        {"ai", "collectors", "database", "signal", "signal_engine", "sqlalchemy"}
    )


def test_attention_occurrence_service_is_application_only() -> None:
    imports = imported_roots("intelligence/services/attention_occurrence.py")
    assert imports.isdisjoint(
        {"ai", "collectors", "database", "signal", "signal_engine", "sqlalchemy"}
    )


@pytest.mark.parametrize(
    "extractor_module",
    ["ai/extractors/base.py", "ai/extractors/mock.py"],
)
def test_opinion_extractors_do_not_cross_service_boundaries(extractor_module: str) -> None:
    imports = imported_roots(extractor_module)
    assert imports.isdisjoint({"database", "intelligence", "signal", "signal_engine", "sqlalchemy"})


def test_opinion_processing_service_does_not_depend_on_state_or_signal() -> None:
    imports = imported_roots("ai/services/opinion_processing.py")
    assert imports.isdisjoint({"intelligence", "signal", "signal_engine"})


@pytest.mark.parametrize(
    "policy_module",
    [
        "intelligence/policies/attention.py",
        "intelligence/policies/asset_aggregation.py",
        "intelligence/policies/consensus.py",
        "intelligence/policies/inclusion.py",
        "intelligence/policies/investor_weight.py",
        "intelligence/policies/state_reducer.py",
        "intelligence/policies/transition.py",
    ],
)
def test_state_policies_are_pure(policy_module: str) -> None:
    imports = imported_roots(policy_module)
    assert imports.isdisjoint({"ai", "database", "signal", "signal_engine", "sqlalchemy"})


def test_state_update_service_does_not_depend_on_ai_or_signal() -> None:
    imports = imported_roots("intelligence/services/state_update.py")
    assert imports.isdisjoint({"ai", "signal", "signal_engine"})


def test_asset_intelligence_service_does_not_cross_forbidden_boundaries() -> None:
    imports = imported_roots("intelligence/services/asset_intelligence.py")
    assert imports.isdisjoint({"ai", "collectors", "signal", "signal_engine"})


def test_core_intelligence_pipeline_has_no_infrastructure_or_signal_dependency() -> None:
    imports = imported_roots("pipeline/intelligence_pipeline.py")
    assert imports.isdisjoint({"collectors", "database", "signal", "signal_engine", "sqlalchemy"})


def test_collector_package_boundaries_are_source_only() -> None:
    assert_package_boundary(
        "collectors",
        {"ai", "database", "intelligence", "signal", "signal_engine", "sqlalchemy"},
        exclude={"collectors/xueqiu/smoke.py"},
    )


def test_extractor_package_boundaries_are_provider_neutral() -> None:
    assert_package_boundary(
        "ai/extractors",
        {"database", "intelligence", "signal", "signal_engine", "sqlalchemy"},
    )


def test_openai_sdk_is_confined_to_provider_adapter() -> None:
    forbidden = {"openai"}
    checked_packages = (
        "ai/services",
        "contracts",
        "intelligence",
        "signal_engine",
        "pipeline",
        "database/models",
    )
    violations = {
        module: sorted(imported_roots(module) & forbidden)
        for package in checked_packages
        for module in package_modules(package)
        if imported_roots(module) & forbidden
    }
    assert violations == {}


def test_openai_provider_adapter_is_the_only_sdk_boundary() -> None:
    assert "openai" in imported_roots("ai/extractors/openai_compatible.py")


def test_core_layers_have_no_provider_name_special_cases() -> None:
    forbidden_tokens = {
        "volcengine",
        "deepseek",
        "glm",
        "openrouter",
        "siliconflow",
    }
    checked_packages = (
        "ai/services",
        "contracts",
        "intelligence",
        "pipeline",
        "database/models",
    )
    violations = {
        module: sorted(
            token
            for token in forbidden_tokens
            if token in (PROJECT_ROOT / module).read_text(encoding="utf-8").lower()
        )
        for package in checked_packages
        for module in package_modules(package)
        if any(
            token in (PROJECT_ROOT / module).read_text(encoding="utf-8").lower()
            for token in forbidden_tokens
        )
    }
    assert violations == {}


def test_ai_service_package_does_not_cross_state_or_signal_boundaries() -> None:
    assert_package_boundary("ai/services", {"intelligence", "signal", "signal_engine"})


def test_policy_package_is_pure() -> None:
    assert_package_boundary(
        "intelligence/policies",
        {"ai", "database", "signal", "signal_engine", "sqlalchemy"},
    )


def test_intelligence_service_package_does_not_depend_on_ai_or_signal() -> None:
    assert_package_boundary(
        "intelligence/services",
        {"ai", "collectors", "signal", "signal_engine", "sqlalchemy"},
    )


def test_pipeline_package_has_no_infrastructure_or_signal_dependency() -> None:
    assert_package_boundary(
        "pipeline",
        {"database", "signal", "signal_engine", "sqlalchemy"},
        exclude={"pipeline/demo.py"},
    )
