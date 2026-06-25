from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_channel_list_does_not_expose_retired_program_availability_filter() -> None:
    source = (PROJECT_ROOT / "aicrm_next" / "automation_engine" / "channels_api.py").read_text(encoding="utf-8")

    assert "available_for_program_id" not in source
    assert "automation_program_channel_binding" not in source
