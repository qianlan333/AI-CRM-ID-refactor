from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_old_automation_conversion_fixtures_are_removed() -> None:
    assert not (ROOT / "tests" / "fixtures" / "old_automation_conversion").exists()


def test_retired_reply_monitor_readiness_tool_is_removed() -> None:
    assert not (ROOT / "tools" / "check_reply_monitor_run_due_readiness.py").exists()
