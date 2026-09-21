from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def read_script(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_runtime_scripts_define_processes_and_cdp_boundary() -> None:
    start = read_script("start-runtime.ps1")
    assert "operations.scheduler" in start
    assert "backend.app.main:app" in start
    assert "npm.cmd" in start
    assert "--remote-debugging-port=" in start
    assert "ACTION_REQUIRED" in start
    assert ".local\\edge-cdp-profile" in start


def test_runtime_scripts_do_not_embed_secrets_or_semantic_pipeline_commands() -> None:
    for name in (
        "start-runtime.ps1",
        "stop-runtime.ps1",
        "runtime-status.ps1",
        "install-runtime-task.ps1",
    ):
        text = read_script(name).lower()
        assert "password" not in text
        assert "cookie" not in text
        assert "api_key" not in text
        assert "operations.refresh" not in text


def test_runtime_processes_are_not_internal_restart_loops() -> None:
    start = read_script("start-runtime.ps1")
    assert "while (" not in start
    assert "for(" in start
    assert "Start-ServiceProcess" in start


def test_stop_is_scoped_to_project_owned_processes() -> None:
    stop = read_script("stop-runtime.ps1")
    assert "ProjectRoot" in stop
    assert "SKIPPED_PID_NOT_OWNED" in stop
    assert "Stop-Process" in stop
    assert "Remove-Item -Recurse" not in stop
