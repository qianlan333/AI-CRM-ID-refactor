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
from tools.check_legacy_facade_growth_freeze import check_aicrm_next_legacy_import_boundary
from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml

DOC = ROOT / "docs/development/phase_7b_baseline_legacy_import_remediation.md"
PLAN_YAML = ROOT / "docs/development/phase_7b_baseline_legacy_import_remediation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase7b_baseline_legacy_import_remediation.py"
NEXT_BUNDLE = "phase_7c_delete_ready_candidate_selection_bundle"
FALSE_AUTHORIZATIONS = {
    "fallback_removal_authorized",
    "production_compat_behavior_change_authorized",
    "legacy_runtime_deletion_authorized",
    "destructive_migration_authorized",
    "delete_ready",
    "timer_execution_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "live_wecom_behavior_change_authorized",
}
REMEDIATED_IMPORTS = {
    "wecom_ability_service.domains.tasks.private_message",
    "wecom_ability_service.wecom_client",
    "wecom_ability_service.domains.broadcast_jobs",
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/automation_engine/group_ops/domain.py",
    "aicrm_next/integration_gateway/legacy_flask_facade.py",
    "aicrm_next/integration_gateway/wecom_group_adapter.py",
    "docs/development/phase_7b_baseline_legacy_import_remediation.md",
    "docs/development/phase_7b_baseline_legacy_import_remediation.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase7b_baseline_legacy_import_remediation.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase7b_baseline_legacy_import_remediation.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py", "docs/route_ownership/production_route_ownership_manifest.yaml"}
FORBIDDEN_PREFIXES = ("wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")


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


def _read(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


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
    if data.get("bundle_type") != "phase_7b_baseline_legacy_import_remediation_bundle":
        blockers.append("bundle_type must be phase_7b_baseline_legacy_import_remediation_bundle")
    if data.get("cleanup_family") != "baseline_direct_legacy_import_remediation":
        blockers.append("cleanup_family must be baseline_direct_legacy_import_remediation")

    target = _dict(data.get("target_blockers"))
    if target.get("before_count") != 3:
        blockers.append("target_blockers.before_count must be 3")
    if target.get("after_count") != 0:
        blockers.append("target_blockers.after_count must be 0")
    remediated = _list(target.get("remediated"))
    imports = {str(item.get("previous_import")) for item in remediated if isinstance(item, dict)}
    if REMEDIATED_IMPORTS - imports:
        blockers.append(f"target_blockers.remediated missing imports: {sorted(REMEDIATED_IMPORTS - imports)}")
    for item in remediated:
        if _dict(item).get("behavior_change_expected") is not False:
            blockers.append("each remediated import must declare behavior_change_expected false")
        if _dict(item).get("boundary") != "aicrm_next/integration_gateway/legacy_flask_facade.py":
            blockers.append("each remediated import must use legacy_flask_facade boundary")

    boundary = _dict(data.get("boundary_refactor"))
    for key in ("runtime_deleted", "fallback_removed", "production_compat_changed", "live_wecom_behavior_changed", "group_ops_behavior_changed"):
        if boundary.get(key) is not False:
            blockers.append(f"boundary_refactor.{key} must be false")
    if boundary.get("direct_legacy_imports_remaining") != 0:
        blockers.append("boundary_refactor.direct_legacy_imports_remaining must be 0")

    authorizations = _dict(data.get("authorizations"))
    for key in sorted(FALSE_AUTHORIZATIONS):
        if authorizations.get(key) is not False:
            blockers.append(f"authorizations.{key} must be false")

    legacy_boundary = check_aicrm_next_legacy_import_boundary(ROOT)
    details["legacy_import_boundary"] = legacy_boundary
    if not legacy_boundary.get("ok"):
        blockers.append(f"legacy import boundary checker must pass: {legacy_boundary.get('findings')}")
    for relpath in ("aicrm_next/automation_engine/group_ops/domain.py", "aicrm_next/integration_gateway/wecom_group_adapter.py"):
        text = _read(relpath)
        for legacy_import in REMEDIATED_IMPORTS:
            if f"from {legacy_import} import" in text or f"import {legacy_import}" in text:
                blockers.append(f"{relpath} still directly imports {legacy_import}")

    if "def build_legacy_private_message_request_payload" not in _read("aicrm_next/integration_gateway/legacy_flask_facade.py"):
        blockers.append("legacy_flask_facade must expose build_legacy_private_message_request_payload")
    if "def legacy_wecom_client_from_app" not in _read("aicrm_next/integration_gateway/legacy_flask_facade.py"):
        blockers.append("legacy_flask_facade must expose legacy_wecom_client_from_app")
    if "def legacy_broadcast_enqueue_job" not in _read("aicrm_next/integration_gateway/legacy_flask_facade.py"):
        blockers.append("legacy_flask_facade must expose legacy_broadcast_enqueue_job")

    evidence = _dict(data.get("verification_evidence"))
    for key in ("production_behavior_unchanged", "fallback_retained", "production_compat_unchanged"):
        if evidence.get(key) is not True:
            blockers.append(f"verification_evidence.{key} must be true")
    if evidence.get("legacy_facade_growth_freeze") != "pass":
        blockers.append("verification_evidence.legacy_facade_growth_freeze must be pass")

    if state.get("current_phase") != "phase_7b_baseline_legacy_import_remediation":
        blockers.append("phase_execution_state.current_phase must be Phase 7B")
    if state.get("active_candidate") != "phase_7_baseline_legacy_import_remediation":
        blockers.append("phase_execution_state.active_candidate must be phase_7_baseline_legacy_import_remediation")
    if state.get("last_merged_pr") != "#774":
        blockers.append("phase_execution_state.last_merged_pr must record PR #774")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 7C")
    if state.get("next_allowed_actions") != [NEXT_BUNDLE]:
        blockers.append("phase_execution_state.next_allowed_actions must contain only Phase 7C")
    phase_state = _dict(state.get("phase7b_baseline_legacy_import_remediation"))
    if phase_state.get("baseline_direct_legacy_import_blockers_before") != 3:
        blockers.append("phase7b state before blocker count must be 3")
    if phase_state.get("baseline_direct_legacy_import_blockers_after") != 0:
        blockers.append("phase7b state after blocker count must be 0")
    if phase_state.get("delete_ready") is not False:
        blockers.append("phase7b state delete_ready must be false")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 7B allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 7B Baseline Legacy Import Remediation Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
