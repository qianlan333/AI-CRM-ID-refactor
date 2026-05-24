from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4t_profile_segment_template_readonly_dry_run_review.py"
PLAN_YAML = ROOT / "docs/development/phase_4t_profile_segment_template_readonly_dry_run_review.yaml"
PLAN_MD = ROOT / "docs/development/phase_4t_profile_segment_template_readonly_dry_run_review.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml() -> dict:
    return _load_module(CHECKER, "phase4t_checker").load_yaml(PLAN_YAML)


def test_checker_current_repo_passes() -> None:
    proc = subprocess.run(
        ["python3", str(CHECKER.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout
    assert "overall: PASS" in proc.stdout


def test_yaml_flags_false() -> None:
    data = _load_yaml()
    for field in (
        "production_write_authorized",
        "production_repository_route_enablement_authorized",
        "production_route_ownership_switch_authorized",
        "fallback_removal_authorized",
        "production_compat_change_authorized",
        "production_write_canary_authorized",
        "real_external_call_authorized",
        "delete_ready",
    ):
        assert data[field] is False


def test_evidence_review_complete() -> None:
    review = _load_yaml()["evidence_review"]
    assert review["result_status"] == "blocked_only_no_production_dry_run_executed"
    assert review["phase_4s_evidence_present"] is True
    assert review["production_readonly_dry_run_executed"] is False
    assert review["blocked_evidence_only"] is True
    assert review["writes_attempted"] is False
    assert review["route_owner_changed"] is False
    assert review["production_compat_changed"] is False
    assert review["fallback_retained"] is True
    assert review["blockers"]


def test_blocked_no_execution_evidence_cannot_mark_route_switch_ready() -> None:
    data = _load_yaml()
    assert data["evidence_review"]["production_readonly_dry_run_executed"] is False
    assert data["route_switch_readiness"]["ready"] is False


def test_required_before_ready_complete() -> None:
    required = set(_load_yaml()["route_switch_readiness"]["required_before_ready"])
    assert required >= {
        "actual_production_readonly_dry_run_executed",
        "read_parity_passed",
        "no_writes_attempted",
        "side_effect_safety_false",
        "fallback_validation_passed",
        "production_compat_unchanged",
        "owner_approval_completed",
        "rollback_owner_assigned",
        "production_config_review_completed",
    }


def test_phase4u_recommendation_blocks_unsafe_next_steps() -> None:
    rec = _load_yaml()["phase_4u_recommendation"]
    assert "read_only_dry_run_execution_evidence" in rec["recommended_next_step"]
    assert rec["production_write_allowed"] is False
    assert rec["production_route_switch_allowed"] is False
    assert rec["fallback_removal_allowed"] is False
    assert rec["production_write_canary_allowed"] is False


def test_no_runtime_files_changed_if_git_available() -> None:
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
    assert not any(path.startswith("aicrm_next/") for path in changed)
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)
    assert "app.py" not in changed
    assert "legacy_flask_app.py" not in changed


def test_docs_do_not_claim_forbidden_states() -> None:
    text = PLAN_MD.read_text(encoding="utf-8").lower()
    for forbidden in (
        "production write executed",
        "production repository enabled as route owner",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ):
        assert forbidden not in text
