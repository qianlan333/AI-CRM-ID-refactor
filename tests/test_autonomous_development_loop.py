from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_autonomous_development_loop as checker


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STOP = ROOT / "docs/development/autonomous_stop_conditions.yaml"
DOC = ROOT / "docs/development/autonomous_development_loop.md"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_phase_execution_state_uses_compact_active_contract() -> None:
    data = checker.load_yaml(STATE)
    assert checker.REQUIRED_STATE_FIELDS <= set(data)
    assert data["current_phase"] == "runtime_fallback_migration"
    assert data["last_merged_pr"] == "#862"
    assert data["last_merged_cleanup_wave"] == "final_non_runtime_cleanup_closeout_wave17"
    assert data["recommended_next_pr"] == "runtime_fallback_migration_channels_track1"
    assert data["owner_approval_required"] is False
    assert data["runtime_behavior_changed"] is False
    assert data["delete_ready"] is False
    assert "completed_steps" not in data
    assert "active_candidate" not in data
    assert "action_templates_readiness" not in data


def test_active_safety_gates_are_current() -> None:
    data = checker.load_yaml(STATE)
    assert set(data["active_safety_gates"]) == checker.EXPECTED_SAFETY_GATES
    assert "check_legacy_facade_growth_freeze" in data["active_safety_gates"]
    assert "generate_legacy_replacement_backlog" in data["active_safety_gates"]
    assert "check_production_route_resolution" in data["active_safety_gates"]
    assert "pr_smoke" in data["active_safety_gates"]


def test_protected_runtime_boundaries_are_retained() -> None:
    data = checker.load_yaml(STATE)
    assert set(data["protected_runtime_boundaries"]) == checker.EXPECTED_RUNTIME_BOUNDARIES
    assert "app.py" in data["protected_runtime_boundaries"]
    assert "legacy_flask_app.py" in data["protected_runtime_boundaries"]
    assert "aicrm_next/production_compat/api.py selected low/medium fallback entries only" in data["protected_runtime_boundaries"]
    assert "wecom_ability_service runtime" in data["protected_runtime_boundaries"]


def test_next_cleanup_candidates_select_runtime_fallback_track() -> None:
    data = checker.load_yaml(STATE)
    assert data["next_cleanup_candidates"] == checker.EXPECTED_NEXT_CANDIDATES
    assert data["next_cleanup_candidates"]["non_runtime_cleanup"] == "complete"
    assert data["next_cleanup_candidates"]["runtime_fallback_cleanup"] == "active_low_medium_admin_track"
    assert data["next_cleanup_candidates"]["high_risk_external_cleanup"] == "separate_owner_approval_required"


def test_autopilot_settings_allow_bounded_runtime_fallback_without_admin_override() -> None:
    data = checker.load_yaml(STATE)
    autopilot = data["autopilot"]
    assert autopilot["enabled"] is True
    assert autopilot["mode"] == "bounded_runtime_fallback_migration"
    assert autopilot["runtime_changes_allowed"] is True
    assert autopilot["admin_override_allowed"] is False


def test_stop_conditions_complete() -> None:
    data = checker.load_yaml(STOP)
    ids = {item["id"] for item in data["high_risk_stop_conditions"]}
    assert checker.STOP_IDS <= ids


def test_docs_include_required_autopilot_contract_sections() -> None:
    text = DOC.read_text(encoding="utf-8")
    for section in ("Business value", "Business continuity", "Risk / rollback", "Next action"):
        assert section in text


def test_no_runtime_or_protected_files_changed_if_git_diff_available() -> None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    assert "app.py" not in changed
    assert "legacy_flask_app.py" not in changed
    assert "aicrm_next/main.py" not in changed
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)
    assert not any(path.startswith("deploy/") for path in changed)
