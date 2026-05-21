from __future__ import annotations

import pytest
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    (PROJECT_ROOT / "docs/d9_6_openclaw_physical_deletion_report.md").exists()
    and not (PROJECT_ROOT / "openclaw_service").exists(),
    reason="Superseded by D9.6 physical deletion state",
)



def _read(relpath: str) -> str:
    return (PROJECT_ROOT / relpath).read_text(encoding="utf-8")


def test_d9_5_2_docs_exist() -> None:
    assert (PROJECT_ROOT / "docs/d9_5_2_openclaw_shim_deletion_blocked_summary.md").exists()
    assert (PROJECT_ROOT / "docs/d9_5_2_openclaw_observation_collection_runbook.md").exists()
    assert (PROJECT_ROOT / "docs/d9_5_2_openclaw_deletion_pr_preflight_checklist.md").exists()


def test_openclaw_shim_and_archive_still_exist() -> None:
    assert (PROJECT_ROOT / "openclaw_service").is_dir()
    assert (PROJECT_ROOT / "openclaw_service/__init__.py").exists()
    assert (PROJECT_ROOT / "legacy_flask/openclaw_legacy").is_dir()


def test_summary_says_deletion_candidate_false() -> None:
    text = _read("docs/d9_5_2_openclaw_shim_deletion_blocked_summary.md")
    assert "Deletion candidate: false" in text


def test_docs_mention_pending_observation_evidence() -> None:
    summary = _read("docs/d9_5_2_openclaw_shim_deletion_blocked_summary.md")
    runbook = _read("docs/d9_5_2_openclaw_observation_collection_runbook.md")
    assert "missing real observation window and production evidence" in summary
    assert "not_available_in_local_environment" in runbook


def test_docs_do_not_use_forbidden_status_markers() -> None:
    docs = [
        "docs/d9_5_2_openclaw_shim_deletion_blocked_summary.md",
        "docs/d9_5_2_openclaw_observation_collection_runbook.md",
        "docs/d9_5_2_openclaw_deletion_pr_preflight_checklist.md",
    ]
    for relpath in docs:
        text = _read(relpath)
        for marker in ["delete_ready", "production_ready", "production_approved"]:
            assert marker not in text


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d9_5_2_openclaw_deletion_blocked_status")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["summary_exists"] is True
    assert result["runbook_exists"] is True
    assert result["preflight_checklist_exists"] is True
    assert result["openclaw_service_still_exists"] is True
    assert result["shim_still_exists"] is True
    assert result["legacy_flask_openclaw_legacy_exists"] is True
    assert result["deletion_candidate"] is False
    assert result["observation_status"] == "pending_observation_evidence"
    assert result["aicrm_next_imports_openclaw_service"] is False
    assert result["production_config_modified"] is False


def test_checker_fails_if_shim_missing(tmp_path, monkeypatch) -> None:
    checker = importlib.import_module("tools.check_d9_5_2_openclaw_deletion_blocked_status")
    monkeypatch.setattr(checker, "PROJECT_ROOT", tmp_path)
    (tmp_path / "openclaw_service").mkdir()
    (tmp_path / "legacy_flask/openclaw_legacy").mkdir(parents=True)
    blockers: list[dict] = []
    result = checker._check_retained_paths(blockers)
    assert result["shim_still_exists"] is False
    assert any(item["reason"] == "openclaw_service_shim_missing" for item in blockers)


def test_production_config_not_modified() -> None:
    checker = importlib.import_module("tools.check_d9_5_2_openclaw_deletion_blocked_status")
    blockers: list[dict] = []
    result = checker._check_production_config_modified(blockers)
    assert result["production_config_modified"] is False
