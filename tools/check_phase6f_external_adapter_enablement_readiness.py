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

DOC = ROOT / "docs/development/phase_6f_external_adapter_enablement_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_6f_external_adapter_enablement_readiness.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6f_external_adapter_enablement_readiness.py"
REQUIRED_FAMILIES = {
    "wecom_tags",
    "wecom_customer_contact_callback",
    "oauth_identity",
    "media_upload",
    "payment_commerce",
    "openclaw_mcp_ai_assist",
    "questionnaire_external_submit",
}
SELECTED = {"media_upload", "wecom_tags", "openclaw_mcp_ai_assist"}
EXCLUDED = {"payment_commerce", "oauth_identity", "wecom_customer_contact_callback", "questionnaire_external_submit"}
REQUIRED_FIELDS = {
    "family_name",
    "route_family",
    "capability_owner",
    "phase_5_acceptance_status",
    "live_adapter_available",
    "canary_tooling_available",
    "production_canary_passed",
    "recommended_phase6_status",
    "risk_level",
    "enablement_ready",
    "blocked_reasons",
    "required_approvals",
    "rollback_requirement",
    "recommended_next_bundle",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6f_external_adapter_enablement_readiness.md",
    "docs/development/phase_6f_external_adapter_enablement_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6f_external_adapter_enablement_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6f_external_adapter_enablement_readiness.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py"}


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
    if data.get("bundle_type") != "phase_6f_external_adapter_enablement_readiness_bundle":
        blockers.append("bundle_type must be phase_6f_external_adapter_enablement_readiness_bundle")
    if data.get("route_family") != "phase_6_external_adapter_enablement_readiness":
        blockers.append("route_family must be phase_6_external_adapter_enablement_readiness")

    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    required_auth = {
        "live_external_enablement_authorized",
        "production_owner_switch_authorized",
        "production_compat_change_authorized",
        "fallback_removal_authorized",
        "timer_execution_authorized",
        "automation_execution_authorized",
        "outbound_send_authorized",
        "payment_capture_authorized",
        "oauth_callback_cutover_authorized",
        "delete_ready",
    }
    if required_auth - set(_dict(data.get("authorizations"))):
        blockers.append(f"authorizations missing keys: {sorted(required_auth - set(_dict(data.get('authorizations'))))}")

    inventory = _list(data.get("candidate_inventory"))
    by_key = {str(item.get("family_key")): item for item in inventory if isinstance(item, dict)}
    if set(by_key) != REQUIRED_FAMILIES:
        blockers.append(f"candidate_inventory must contain required families: {sorted(REQUIRED_FAMILIES)}")
    for key, item in by_key.items():
        missing_fields = sorted(REQUIRED_FIELDS - set(item))
        if missing_fields:
            blockers.append(f"{key} missing required fields: {missing_fields}")
        if item.get("phase_5_acceptance_status") != "family_acceptance_complete":
            blockers.append(f"{key}.phase_5_acceptance_status must be family_acceptance_complete")
        if item.get("production_canary_passed") is not False:
            blockers.append(f"{key}.production_canary_passed must be false")
        if not _list(item.get("blocked_reasons")):
            blockers.append(f"{key}.blocked_reasons must be non-empty")
        if not _list(item.get("required_approvals")):
            blockers.append(f"{key}.required_approvals must be non-empty")
        if not item.get("rollback_requirement"):
            blockers.append(f"{key}.rollback_requirement must be non-empty")
        if key in SELECTED and item.get("enablement_ready") is not True:
            blockers.append(f"{key}.enablement_ready must be true for selected candidates")
        if key in EXCLUDED and item.get("enablement_ready") is not False:
            blockers.append(f"{key}.enablement_ready must be false for explicitly excluded candidates")

    first = _dict(data.get("first_phase6g_candidates"))
    if set(_list(first.get("selected"))) != SELECTED:
        blockers.append("first_phase6g_candidates.selected must select media_upload, wecom_tags, and openclaw_mcp_ai_assist")
    if set(_list(first.get("explicitly_not_selected"))) != EXCLUDED:
        blockers.append("first_phase6g_candidates.explicitly_not_selected must exclude high-risk families")
    for key, value in _dict(first.get("selection_rules")).items():
        if value is not True:
            blockers.append(f"first_phase6g_candidates.selection_rules.{key} must be true")

    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _list(data.get("next")) != ["phase_6g_low_risk_external_adapter_enablement_tooling_bundle"]:
        blockers.append("next must only recommend Phase 6G low-risk external adapter enablement tooling")

    if state.get("current_phase") != "phase_6f_external_adapter_enablement_readiness":
        blockers.append("phase_execution_state.current_phase must be Phase 6F")
    if state.get("active_candidate") != "external_adapter_enablement_readiness":
        blockers.append("phase_execution_state.active_candidate must be external_adapter_enablement_readiness")
    if state.get("last_merged_pr") != "#764":
        blockers.append("phase_execution_state.last_merged_pr must record PR #764")
    if state.get("recommended_next_pr") != "phase_6g_low_risk_external_adapter_enablement_tooling_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6G")
    if state.get("next_allowed_actions") != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6F allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6F External Adapter Enablement Readiness Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
