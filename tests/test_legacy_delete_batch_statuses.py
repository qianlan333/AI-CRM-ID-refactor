from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _section(source: str, batch: str) -> str:
    return source.split(f"## {batch}:", 1)[1].split("\n## ", 1)[0]


def _status(source: str, batch: str) -> str:
    section = _section(source, batch)
    return next(line.strip() for line in section.splitlines() if line.strip().lower().startswith("status:"))


def test_legacy_delete_batch_statuses_match_d1_to_d6_5_state() -> None:
    source = _read("docs/legacy_delete_batches.md")

    assert _status(source, "D1").lower() == "status: retired/deleted."
    assert _status(source, "D2").lower() == "status: retired/deleted."
    assert _status(source, "D3").lower() == "status: retired/deleted."
    assert _status(source, "D4").lower() == "status: retired/tombstoned."
    assert _status(source, "D5").lower() == "status: retired/tombstoned."
    assert _status(source, "D6").lower() == "status: retired/tombstoned."
    assert _status(source, "D6.5").lower() == "status: completed for no-reference readonly leftovers only."


def test_future_delete_batches_remain_blocked_or_not_started() -> None:
    source = _read("docs/legacy_delete_batches.md")

    for batch in ("D7", "D8", "D9"):
        status = _status(source, batch).lower()
        assert not status.startswith("status: retired")
        assert not status.startswith("status: deleted")
        assert not status.startswith("status: completed")

    assert "Delete only after real write/external replacement evidence" in _section(source, "D7")
    assert "Delete only after all legacy routes are retired" in _section(source, "D8")
    assert "Delete only after OpenClaw replacement evidence" in _section(source, "D9")


def test_d6_5_physical_deletions_match_dead_code_inventory() -> None:
    delete_batches = _read("docs/legacy_delete_batches.md")
    inventory = _read("docs/legacy_dead_code_inventory.md")

    for path in (
        "wecom_ability_service/templates/admin_console/attachment_library.html",
        "docs/generated/route_inventory.md",
        "docs/generated/route_inventory.json",
    ):
        assert f"- `{path}`" in _section(delete_batches, "D6.5")
        assert f"| {path} |" in inventory
        assert "| delete |" in next(line for line in inventory.splitlines() if line.startswith(f"| {path} |"))


def test_d7_blocker_matrix_remains_non_delete_ready() -> None:
    matrix = _read("docs/d7_write_external_blocker_matrix.md")

    for marker in ("delete_ready", "production_ready", "production_approved"):
        assert marker not in matrix
    for capability in (
        "WeChat Pay checkout / notify",
        "Questionnaire OAuth",
        "Automation OpenClaw push",
        "MCP / OpenClaw legacy adapter",
    ):
        assert capability in matrix


def test_current_retirement_docs_do_not_reopen_completed_readonly_batches() -> None:
    current_docs = "\n".join(
        _read(path)
        for path in (
            "docs/legacy_retirement_plan.md",
            "docs/legacy_delete_batches.md",
        )
    )

    stale_status = "not" + " started"
    for stale_phrase in (
        "D4 User Ops old routes have " + stale_status,
        "D5 Questionnaire old routes have " + stale_status,
        "D6 Automation old routes have " + stale_status,
    ):
        assert stale_phrase not in current_docs

    assert "D1 Media Library old Flask route modules are retired/deleted" in current_docs
    assert "D2 Product Management old Flask admin route owner is retired/deleted" in current_docs
    assert "D3 Customer Read Model old Flask readonly route owner is retired/deleted" in current_docs
    assert "D4 User Ops old Flask readonly route owner is retired/tombstoned" in current_docs
    assert "D5 Questionnaire old Flask readonly route registrations are retired/tombstoned" in current_docs
    assert "D6 Automation old Flask readonly route registrations are retired/tombstoned" in current_docs
    assert "D6.5 Dead Legacy Cleanup is completed" in current_docs
