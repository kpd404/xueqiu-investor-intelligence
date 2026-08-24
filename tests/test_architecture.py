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
        "pipeline",
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
        "pipeline*",
        "signal_engine*",
    } <= includes


@pytest.mark.parametrize(
    "adapter_module",
    ["collectors/base.py", "collectors/manual/adapter.py"],
)
def test_collector_adapters_do_not_depend_on_persistence_or_ai(adapter_module: str) -> None:
    imports = imported_roots(adapter_module)
    assert imports.isdisjoint({"ai", "database", "sqlalchemy"})


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
