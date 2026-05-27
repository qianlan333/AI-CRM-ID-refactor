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

DOC = ROOT / "docs/development/post_phase7_owner_feature_selection.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_owner_feature_selection.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_owner_feature_selection.py"
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
    "live_wecom_send_authorized",
    "timer_execution_authorized",
    "payment_behavior_authorized",
    "oauth_callback_cutover_authorized",
    "delete_ready",
}
REQUIRED_FALSE_BOUNDARY_FLAGS = {
    "live_wecom_send_allowed",
    "old_flask_broadcast_call_allowed",
    "production_compat_route_allowed",
    "wecom_ability_service_business_logic_allowed",
    "timer_execution_allowed",
    "batch_send_execution_allowed",
    "direct_legacy_import_allowed",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_owner_feature_selection.md",
    "docs/development/post_phase7_owner_feature_selection.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_owner_feature_selection.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_owner_feature_selection.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py", "docs/route_ownership/production_route_ownership_manifest.yaml"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
    if data.get("bundle_type") != "post_phase7_owner_feature_selection_bundle":
        blockers.append("bundle_type must be post_phase7_owner_feature_selection_bundle")
    if data.get("route_family") != "post_phase7_owner_feature_selection":
        blockers.append("route_family must be post_phase7_owner_feature_selection")

    authorizations = _dict(data.get("authorizations"))
    missing_authorizations = sorted(REQUIRED_AUTHORIZATIONS - set(authorizations))
    if missing_authorizations:
        blockers.append(f"authorizations missing: {missing_authorizations}")
    for key in REQUIRED_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    handoff = _dict(data.get("intake_handoff"))
    if handoff.get("source_pr") != 795:
        blockers.append("intake_handoff.source_pr must be 795")
    if handoff.get("source_bundle") != "post_phase7_first_new_feature_intake_bundle":
        blockers.append("intake_handoff.source_bundle must be post_phase7_first_new_feature_intake_bundle")
    if handoff.get("pending_owner_selection_resolved") is not True:
        blockers.append("intake_handoff.pending_owner_selection_resolved must be true")

    selected = _dict(data.get("selected_feature"))
    if not selected.get("selected_feature_id"):
        blockers.append("selected_feature.selected_feature_id must be non-empty")
    if selected.get("selected_feature_id") != "hxc_next_native_broadcast_backend":
        blockers.append("selected_feature.selected_feature_id must be hxc_next_native_broadcast_backend")
    if selected.get("implementation_authorized") is not False:
        blockers.append("selected_feature.implementation_authorized must be false")
    for key in ("capability_owner", "route_family"):
        if not selected.get(key):
            blockers.append(f"selected_feature.{key} must be non-empty")
    for key in ("requires_feature_flag", "requires_canary_before_live_send", "requires_owner_approval"):
        if selected.get(key) is not True:
            blockers.append(f"selected_feature.{key} must be true")
    if selected.get("external_side_effect_in_first_implementation") is not False:
        blockers.append("selected_feature.external_side_effect_in_first_implementation must be false")

    boundary = _dict(data.get("implementation_boundary"))
    if boundary.get("first_pr_may_implement_contract_or_plan_only") is not True:
        blockers.append("implementation_boundary.first_pr_may_implement_contract_or_plan_only must be true")
    for key in REQUIRED_FALSE_BOUNDARY_FLAGS:
        if boundary.get(key) is not False:
            blockers.append(f"implementation_boundary.{key} must be false")

    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != "post_phase7_hxc_next_native_broadcast_backend_plan_bundle":
        blockers.append("next_bundle.recommended_next_step must be post_phase7_hxc_next_native_broadcast_backend_plan_bundle")
    if not next_bundle.get("route_family"):
        blockers.append("next_bundle.route_family must be non-empty")

    if state.get("current_phase") != "post_phase7_owner_feature_selection":
        blockers.append("phase_execution_state.current_phase must be post_phase7_owner_feature_selection")
    if state.get("active_candidate") != "post_phase7_owner_feature_selection":
        blockers.append("phase_execution_state.active_candidate must be post_phase7_owner_feature_selection")
    if state.get("last_merged_pr") != "#795":
        blockers.append("phase_execution_state.last_merged_pr must record PR #795")
    if state.get("next_allowed_actions") != ["post_phase7_hxc_next_native_broadcast_backend_plan_bundle"]:
        blockers.append("phase_execution_state.next_allowed_actions must recommend HXC plan bundle only")
    phase_state = _dict(state.get("post_phase7_owner_feature_selection"))
    if phase_state.get("selected_feature_id") != "hxc_next_native_broadcast_backend":
        blockers.append("post_phase7 owner selection state must record selected HXC feature")
    for key in (
        "business_feature_implemented",
        "runtime_route_changed",
        "schema_migration_added",
        "production_compat_route_added",
        "wecom_ability_service_business_logic_added",
        "direct_legacy_import_added",
        "fallback_removed",
        "production_compat_behavior_changed",
        "legacy_runtime_deleted",
        "live_wecom_send_enabled",
        "outbound_send_enabled",
        "timer_execution_enabled",
        "delete_ready",
    ):
        if phase_state.get(key) is not False:
            blockers.append(f"post_phase7 owner selection state {key} must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Post-Phase 7 owner selection allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 Owner Feature Selection Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
