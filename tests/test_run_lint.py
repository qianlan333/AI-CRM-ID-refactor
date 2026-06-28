from __future__ import annotations

import subprocess
from pathlib import Path

import scripts.run_lint as run_lint


def test_run_lint_scope_includes_tools_directory() -> None:
    assert "tools" in run_lint.PYTHON_TARGETS
    assert any(path.name == "tools" for path in run_lint.SCAN_ROOTS)


def test_custom_text_checks_scan_tools_directory(tmp_path, monkeypatch) -> None:
    tool_file = tmp_path / "tools" / "bad_tool.py"
    tool_file.parent.mkdir()
    tool_file.write_text("value = 1    \n", encoding="utf-8")

    monkeypatch.setattr(run_lint, "ROOT", tmp_path)
    monkeypatch.setattr(run_lint, "SCAN_ROOTS", [tmp_path / "tools"])

    assert run_lint._custom_text_checks() == ["tools/bad_tool.py:1: trailing whitespace"]


def test_run_ruff_passes_tools_target(tmp_path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, cwd):  # noqa: ANN001
        calls.append(command)
        assert cwd == tmp_path
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(run_lint, "ROOT", tmp_path)
    monkeypatch.setattr(run_lint.subprocess, "run", fake_run)

    assert run_lint._run_ruff() == 0
    assert calls
    assert calls[0][-1] == "tools"
    assert "scripts/run_lint.py" in calls[0]
