from __future__ import annotations

import json
from pathlib import Path

import tools.check_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence as checker
import tools.run_post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_cleanup_task_groups_shadow_compare_rollback_evidence.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_runner_produces_passed_shadow_and_rollback_reports(tmp_path: Path) -> None:
    shadow = tmp_path / "shadow.json"
    rollback = tmp_path / "rollback.json"
    combined = tmp_path / "combined.json"
    exit_code = runner.main(
        [
            "--latest-main-sha",
            checker.EXPECTED_MAIN_SHA,
            "--shadow-output-json",
            str(shadow),
            "--rollback-output-json",
            str(rollback),
            "--combined-output-json",
            str(combined),
        ]
    )
    assert exit_code == 0
    report = json.loads(combined.read_text(encoding="utf-8"))
    assert report["overall"] == "PASS"
    assert report["shadow_compare"]["shadow_compare_executed"] is True
    assert report["shadow_compare"]["shadow_compare_passed"] is True
    assert report["rollback_rehearsal"]["rollback_rehearsal_executed"] is True
    assert report["rollback_rehearsal"]["rollback_rehearsal_passed"] is True


def test_yaml_records_required_evidence_fields() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["latest_main_sha"] == checker.EXPECTED_MAIN_SHA
    assert data["shadow_compare_output_path"] == "/tmp/task_groups_shadow_compare_evidence.json"
    assert data["shadow_compare_executed"] is True
    assert data["shadow_compare_passed"] is True
    assert data["rollback_rehearsal_output_path"] == "/tmp/task_groups_rollback_rehearsal_evidence.json"
    assert data["rollback_rehearsal_executed"] is True
    assert data["rollback_rehearsal_passed"] is True


def test_no_cleanup_or_runtime_execution_is_authorized() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["authorizations"]["evidence_generation_authorized"] is True
    for key in checker.REQUIRED_FALSE_AUTHORIZATIONS:
        assert data["authorizations"][key] is False
    assert data["production_behavior_changed"] is False
    assert data["fallback_removal_executed"] is False
    assert data["production_compat_cleanup_executed"] is False
    assert data["runtime_deletion_executed"] is False
    assert data["delete_ready"] is False


def test_evidence_details_are_default_safe() -> None:
    details = checker.load_yaml(PLAN_YAML)["evidence_details"]
    assert details["fixture_in_memory_probe_executed"] is True
    assert details["route_ownership_manifest_checked"] is True
    assert details["production_compat_exact_entry_checked"] is True
    assert details["native_route_entry_checked"] is True
    assert details["production_db_connected"] is False
    assert details["production_write_attempted"] is False
    assert details["wildcard_cleanup_required"] is False


def test_next_bundle_returns_to_validation_when_evidence_passes() -> None:
    next_bundle = checker.load_yaml(PLAN_YAML)["next_bundle"]
    assert next_bundle["if_shadow_and_rollback_passed"] == "post_phase7_cleanup_task_groups_owner_evidence_validation_bundle"
    assert next_bundle["if_any_evidence_failed"] == "post_phase7_cleanup_task_groups_shadow_rollback_blocker_acceptance_bundle"


def test_docs_do_not_claim_cleanup_execution_or_delete_ready() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = {
        "fallback removed: true",
        "production_compat cleaned: true",
        "production_compat behavior changed: true",
        "runtime deleted: true",
        "legacy runtime deleted",
        "delete_ready true",
        "delete_ready: true",
    }
    assert not any(claim in text for claim in forbidden_claims)
