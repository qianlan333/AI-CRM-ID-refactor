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
from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml

DOC = ROOT / "docs/development/post_phase7_new_feature_development_rules.md"
PLAN_YAML = ROOT / "docs/development/post_phase7_new_feature_development_rules.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_post_phase7_new_feature_development_rules.py"
REQUIRED_CATEGORIES = {
    "internal_read",
    "internal_write",
    "external_adapter",
    "execution",
    "frontend_component",
    "media",
    "payment",
    "oauth_identity",
    "wecom",
    "cleanup",
}
REQUIRED_FORBIDDEN = {
    "new_production_compat_business_route",
    "new_wecom_ability_service_business_route",
    "new_direct_legacy_import",
    "default_on_external_side_effect",
    "default_on_timer_execution",
    "default_on_outbound_send",
    "unowned_route",
    "route_without_tests",
}
REQUIRED_PR_SECTIONS = {
    "Summary",
    "Business value",
    "Capability owner",
    "Route family",
    "Architecture boundary",
    "Included stages",
    "Excluded stages",
    "Production behavior",
    "Fallback behavior",
    "production_compat behavior",
    "External side effects",
    "Verification",
    "Risk / rollback",
    "PR lifecycle",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/post_phase7_new_feature_development_rules.md",
    "docs/development/post_phase7_new_feature_development_rules.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_post_phase7_new_feature_development_rules.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_post_phase7_new_feature_development_rules.py",
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
    if data.get("bundle_type") != "post_phase7_new_feature_development_rules_bundle":
        blockers.append("bundle_type must be post_phase7_new_feature_development_rules_bundle")
    if data.get("route_family") != "post_phase7_new_feature_development_governance":
        blockers.append("route_family must be post_phase7_new_feature_development_governance")
    handoff = _dict(data.get("phase_7_handoff"))
    for key in ("phase_7_completed", "fallback_retained", "production_compat_retained", "legacy_runtime_retained", "future_cleanup_requires_owner_approval"):
        if handoff.get(key) is not True:
            blockers.append(f"phase_7_handoff.{key} must be true")
    if handoff.get("delete_ready") is not False:
        blockers.append("phase_7_handoff.delete_ready must be false")
    rules = _dict(data.get("default_new_feature_rules"))
    for key in ("new_feature_must_use_next_native_owner", "owner_required", "tests_required", "checker_required", "rollback_required"):
        if rules.get(key) is not True:
            blockers.append(f"default_new_feature_rules.{key} must be true")
    for key in ("production_compat_as_primary_implementation_allowed", "wecom_ability_service_new_business_logic_allowed", "direct_legacy_import_allowed", "fallback_as_primary_path_allowed"):
        if rules.get(key) is not False:
            blockers.append(f"default_new_feature_rules.{key} must be false")
    categories = {str(item.get("category")) for item in _list(data.get("feature_categories")) if isinstance(item, dict)}
    missing_categories = sorted(REQUIRED_CATEGORIES - categories)
    if missing_categories:
        blockers.append(f"feature_categories missing: {missing_categories}")
    forbidden = set(str(item) for item in _list(data.get("forbidden_patterns")))
    missing_forbidden = sorted(REQUIRED_FORBIDDEN - forbidden)
    if missing_forbidden:
        blockers.append(f"forbidden_patterns missing: {missing_forbidden}")
    sections = set(str(item) for item in _list(data.get("required_pr_sections")))
    missing_sections = sorted(REQUIRED_PR_SECTIONS - sections)
    if missing_sections:
        blockers.append(f"required_pr_sections missing: {missing_sections}")
    next_bundle = _dict(data.get("next_bundle"))
    if next_bundle.get("recommended_next_step") != "post_phase7_first_new_feature_intake_bundle":
        blockers.append("next_bundle.recommended_next_step must be post_phase7_first_new_feature_intake_bundle")
    if next_bundle.get("route_family") != "selected_by_owner":
        blockers.append("next_bundle.route_family must be selected_by_owner")
    if state.get("current_phase") != "post_phase7_new_feature_development_rules":
        blockers.append("phase_execution_state.current_phase must be post-phase7 new feature rules")
    if state.get("active_candidate") != "post_phase7_new_feature_development_governance":
        blockers.append("phase_execution_state.active_candidate must be post-phase7 governance")
    if state.get("last_merged_pr") != "#793":
        blockers.append("phase_execution_state.last_merged_pr must record PR #793")
    if state.get("next_allowed_actions") != ["post_phase7_first_new_feature_intake_bundle"]:
        blockers.append("phase_execution_state.next_allowed_actions must only recommend first new feature intake")
    phase_state = _dict(state.get("post_phase7_new_feature_development_rules"))
    if phase_state.get("rules_only") is not True:
        blockers.append("post_phase7 state rules_only must be true")
    for key in ("fallback_removed", "production_compat_behavior_changed", "legacy_runtime_deleted", "delete_ready", "runtime_feature_changed"):
        if phase_state.get(key) is not False:
            blockers.append(f"post_phase7 state {key} must be false")
    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Post-Phase 7 rules allowlist: {unexpected}")
    forbidden_changed = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden_changed:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden_changed}")
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Post-Phase 7 New Feature Development Rules Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
