#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.run_codex_autopilot_tick import load_yaml

DOC = ROOT / "docs/development/post_phase7_first_new_feature_intake.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_first_new_feature_intake.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_first_new_feature_intake.py"
REQUIRED_AUTHORIZATIONS = {
    "business_feature_implementation_authorized",
    "runtime_route_change_authorized",
    "schema_migration_authorized",
    "production_compat_route_authorized",
    "wecom_ability_service_business_logic_authorized",
    "direct_legacy_import_authorized",
    "fallback_removal_authorized",
    "production_compat_behavior_change_authorized",
    "legacy_runtime_deletion_authorized",
    "outbound_send_authorized",
    "timer_execution_authorized",
    "payment_behavior_authorized",
    "oauth_callback_cutover_authorized",
    "wecom_callback_cutover_authorized",
    "delete_ready",
}
REQUIRED_FIELDS = {
    "feature_id",
    "feature_name",
    "business_goal",
    "user_visible_value",
    "capability_owner",
    "route_family",
    "feature_category",
    "external_side_effect",
    "data_schema_impact",
    "production_risk",
    "requires_feature_flag",
    "requires_canary",
    "requires_owner_approval",
    "rollback_requirement",
    "recommended_first_implementation_bundle",
    "blocked_reason",
}
REQUIRED_CANDIDATES = {
    "hxc_next_native_broadcast_backend",
    "campaign_step_standard_send_content_migration",
    "material_picker_remaining_surface_migration",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_first_new_feature_intake.md",
    "docs/development/post_phase7_first_new_feature_intake.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_first_new_feature_intake.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_first_new_feature_intake.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py", "docs/route_ownership/production_route_ownership_manifest.yaml"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _run_git(args: list[str]) -> set[str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _changed_files() -> set[str]:
    return set().union(
        _run_git(["diff", "--name-only", "origin/main...HEAD"]),
        _run_git(["diff", "--name-only"]),
        _run_git(["diff", "--name-only", "--cached"]),
        _run_git(["ls-files", "--others", "--exclude-standard"]),
    )


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}
    for path in (DOC, PLAN_YAML, STATE, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    if data.get("bundle_type") != "post_phase7_first_new_feature_intake_bundle":
        blockers.append("bundle_type must be post_phase7_first_new_feature_intake_bundle")
    if data.get("route_family") != "post_phase7_feature_intake":
        blockers.append("route_family must be post_phase7_feature_intake")

    authorizations = _dict(data.get("authorizations"))
    missing_authorizations = sorted(REQUIRED_AUTHORIZATIONS - set(authorizations))
    if missing_authorizations:
        blockers.append(f"authorizations missing: {missing_authorizations}")
    for key in REQUIRED_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    handoff = _dict(data.get("phase_7_handoff"))
    for key in ("phase_7_completed", "fallback_retained", "production_compat_retained", "legacy_runtime_retained"):
        if handoff.get(key) is not True:
            blockers.append(f"phase_7_handoff.{key} must be true")
    if handoff.get("delete_ready") is not False:
        blockers.append("phase_7_handoff.delete_ready must be false")

    rules = _dict(data.get("post_phase7_rules"))
    for key in ("next_native_required", "owner_required", "tests_required", "checker_required", "rollback_required"):
        if rules.get(key) is not True:
            blockers.append(f"post_phase7_rules.{key} must be true")
    for key in ("production_compat_primary_path_allowed", "wecom_ability_service_new_business_logic_allowed", "direct_legacy_import_allowed"):
        if rules.get(key) is not False:
            blockers.append(f"post_phase7_rules.{key} must be false")

    matrix = _dict(data.get("feature_intake_matrix"))
    fields = set(str(item) for item in _list(matrix.get("required_fields")))
    missing_fields = sorted(REQUIRED_FIELDS - fields)
    if missing_fields:
        blockers.append(f"feature_intake_matrix.required_fields missing: {missing_fields}")

    candidates = _list(data.get("recommended_candidates"))
    if len(candidates) < 3:
        blockers.append("recommended_candidates must contain at least 3 candidates")
    candidate_ids = {str(item.get("feature_id")) for item in candidates if isinstance(item, dict)}
    missing_candidates = sorted(REQUIRED_CANDIDATES - candidate_ids)
    if missing_candidates:
        blockers.append(f"recommended_candidates missing: {missing_candidates}")
    for item in candidates:
        if not isinstance(item, dict):
            blockers.append("recommended_candidates entries must be objects")
            continue
        missing = sorted(REQUIRED_FIELDS - set(item))
        if missing:
            blockers.append(f"recommended candidate {item.get('feature_id')} missing fields: {missing}")

    selected = _dict(data.get("selected_feature"))
    if selected.get("implementation_authorized") is not False:
        blockers.append("selected_feature.implementation_authorized must be false")
    if selected.get("selected_feature_status") == "pending_owner_selection":
        if selected.get("selected_feature_id") != "none":
            blockers.append("selected_feature_id must be none while pending owner selection")
        if selected.get("owner_selection_required") is not True:
            blockers.append("owner_selection_required must be true while pending owner selection")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("if_pending_owner_selection") != "post_phase7_owner_feature_selection_bundle":
        blockers.append("next_bundle.if_pending_owner_selection must be post_phase7_owner_feature_selection_bundle")
    if next_bundle.get("if_selected_feature_ready") != "post_phase7_first_feature_implementation_plan_bundle":
        blockers.append("next_bundle.if_selected_feature_ready must be post_phase7_first_feature_implementation_plan_bundle")

    if state.get("current_phase") != "post_phase7_first_new_feature_intake":
        blockers.append("phase_execution_state.current_phase must be post_phase7_first_new_feature_intake")
    if state.get("active_candidate") != "post_phase7_feature_intake":
        blockers.append("phase_execution_state.active_candidate must be post_phase7_feature_intake")
    if state.get("last_merged_pr") != "#794":
        blockers.append("phase_execution_state.last_merged_pr must record PR #794")
    if state.get("next_allowed_actions") != ["post_phase7_owner_feature_selection_bundle"]:
        blockers.append("phase_execution_state.next_allowed_actions must only recommend owner feature selection")
    phase_state = _dict(state.get("post_phase7_first_new_feature_intake"))
    if phase_state.get("intake_only") is not True:
        blockers.append("post_phase7 intake state intake_only must be true")
    for key in ("business_feature_implemented", "runtime_route_changed", "schema_migration_added", "production_compat_route_added", "wecom_ability_service_business_logic_added", "direct_legacy_import_added", "fallback_removed", "production_compat_behavior_changed", "legacy_runtime_deleted", "delete_ready"):
        if phase_state.get(key) is not False:
            blockers.append(f"post_phase7 intake state {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Post-Phase 7 intake allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 First New Feature Intake Check", "", f"- overall: {report['overall']}", "- blockers:"]
    lines.extend(f"  - {item}" for item in report.get("blockers", []) or ["none"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
