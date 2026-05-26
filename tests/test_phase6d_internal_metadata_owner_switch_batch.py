from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import tools.check_phase6d_internal_metadata_owner_switch_batch as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_6d_internal_metadata_owner_switch_batch.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_selected_and_excluded_route_families() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert set(data["selected_route_families"]) == checker.SELECTED
    excluded = " ".join(data["excluded_route_families"]).lower()
    for item in ("payment", "oauth", "wecom", "media", "openclaw", "timer", "outbound"):
        assert item in excluded


def test_per_route_guardrails() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for item in data["per_route"]:
        assert item["owner_switch_execution_authorized_default"] is False
        assert item["fallback_retained"] is True
        assert item["production_compat_unchanged"] is True
        assert item["shadow_compare_required"] is True
        assert item["rollback_required"] is True
        assert item["execution_forbidden"] is True
        assert item["outbound_send_forbidden"] is True


def test_authorizations_false_and_continuity_true() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())
    assert all(value is True for value in data["business_continuity"].values())


def test_batch_runner_default_blocked_and_non_effectful() -> None:
    proc = subprocess.run([sys.executable, str(checker.RUNNER)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    data = json.loads(proc.stdout)
    assert data["overall"] == "BLOCKED"
    assert set(data["selected_route_families"]) == checker.SELECTED
    for item in data["per_route"]:
        assert item["owner_switch_executed"] is False
        assert item["production_compat_changed"] is False
        assert item["fallback_removed"] is False
        assert item["timer_execution_triggered"] is False
        assert item["automation_execution_triggered"] is False
        assert item["outbound_send_triggered"] is False
        assert item["external_live_call_triggered"] is False
        assert item["delete_ready"] is False


def test_next_bundle_is_phase6e() -> None:
    next_bundle = checker.load_yaml(PLAN_YAML)["next_bundle"]
    assert next_bundle["recommended_next_step"] == "phase_6e_internal_owner_switch_acceptance_bundle"
    assert next_bundle["owner_switch_execution_allowed_default"] is False
    assert next_bundle["production_compat_change_allowed"] is False
    assert next_bundle["fallback_removal_allowed"] is False
