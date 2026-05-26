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

DOC = ROOT / "docs/development/phase_6h_production_compat_exact_route_narrowing_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_6h_production_compat_exact_route_narrowing_readiness.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
TEST = ROOT / "tests/test_phase6h_production_compat_exact_route_narrowing_readiness.py"
RUNNER = ROOT / "tools/run_phase6h_production_compat_exact_route_shadow_compare.py"
EXPECTED_ROUTES = {
    ("GET", "/api/admin/automation-conversion/task-groups"),
    ("GET", "/api/admin/automation-conversion/workflow-nodes"),
    ("GET", "/api/admin/image-library"),
    ("GET", "/api/admin/image-library/facets"),
    ("GET", "/api/admin/wecom/tags"),
    ("GET", "/api/admin/wecom/tags/live/gate"),
    ("GET", "/mcp"),
}
EXCLUDED = {
    "payment_commerce",
    "oauth_callback",
    "wecom_contact_callback",
    "tasks_workflows_execution_adjacent",
    "timer_run_due",
    "outbound_send",
    "public_submit",
    "wildcard_production_compat",
}
FALSE_RUNNER_KEYS = {
    "production_compat_changed",
    "manifest_written",
    "fallback_removed",
    "wildcard_narrowing",
    "owner_switch_executed",
    "live_external_call_executed",
    "outbound_send_executed",
    "timer_execution_triggered",
    "automation_execution_triggered",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_6h_production_compat_exact_route_narrowing_readiness.md",
    "docs/development/phase_6h_production_compat_exact_route_narrowing_readiness.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase6h_production_compat_exact_route_narrowing_readiness.py",
    "tools/run_phase6h_production_compat_exact_route_shadow_compare.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase6h_production_compat_exact_route_narrowing_readiness.py",
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


def _run_runner() -> dict[str, Any]:
    proc = subprocess.run([sys.executable, str(RUNNER.relative_to(ROOT))], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return {"_error": proc.stderr.strip() or proc.stdout.strip()}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid json: {exc}"}


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {}
    for path in (DOC, PLAN_YAML, STATE, TEST, RUNNER):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    if data.get("bundle_type") != "phase_6h_production_compat_exact_route_narrowing_readiness_bundle":
        blockers.append("bundle_type must be phase_6h_production_compat_exact_route_narrowing_readiness_bundle")
    for key, value in _dict(data.get("authorizations")).items():
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")

    routes = _list(data.get("candidate_exact_routes"))
    route_keys = {(str(item.get("method")), str(item.get("exact_route"))) for item in routes if isinstance(item, dict)}
    if route_keys != EXPECTED_ROUTES:
        blockers.append(f"candidate_exact_routes must match expected exact routes: {sorted(EXPECTED_ROUTES)}")
    for item in routes:
        if not isinstance(item, dict):
            continue
        for key in ("proposed_narrowing_only", "shadow_compare_required", "rollback_required"):
            if item.get(key) is not True:
                blockers.append(f"{item.get('exact_route')}.{key} must be true")
        if "*" in str(item.get("exact_route")) or "{path:path}" in str(item.get("exact_route")):
            blockers.append(f"{item.get('exact_route')} must be exact, not wildcard")

    excluded = {str(item.get("family")) for item in _list(data.get("excluded_routes")) if isinstance(item, dict)}
    if excluded != EXCLUDED:
        blockers.append(f"excluded_routes must contain {sorted(EXCLUDED)}")

    runner_cfg = _dict(data.get("runner"))
    if runner_cfg.get("default_result_status") != "proposed_narrowing_only":
        blockers.append("runner.default_result_status must be proposed_narrowing_only")
    for key in FALSE_RUNNER_KEYS:
        if runner_cfg.get(key) is not False:
            blockers.append(f"runner.{key} must be false")
    for key, value in _dict(data.get("business_continuity")).items():
        if value is not True:
            blockers.append(f"business_continuity.{key} must be true")
    if _list(data.get("next")) != ["phase_6i_external_enablement_and_compat_readiness_acceptance_bundle"]:
        blockers.append("next must only recommend Phase 6I acceptance")

    evidence = _run_runner()
    details["runner_evidence"] = evidence
    if evidence.get("ok") is not True:
        blockers.append("runner ok must be true")
    if evidence.get("result_status") != "proposed_narrowing_only":
        blockers.append("runner result_status must be proposed_narrowing_only")
    for key in FALSE_RUNNER_KEYS:
        if evidence.get(key) is not False:
            blockers.append(f"runner evidence {key} must be false")
    evidence_routes = {(str(item.get("method")), str(item.get("exact_route"))) for item in _list(evidence.get("proposed_routes")) if isinstance(item, dict)}
    if evidence_routes != EXPECTED_ROUTES:
        blockers.append("runner proposed_routes must match YAML candidate_exact_routes")

    if state.get("current_phase") != "phase_6h_production_compat_exact_route_narrowing_readiness":
        blockers.append("phase_execution_state.current_phase must be Phase 6H")
    if state.get("active_candidate") != "production_compat_exact_route_narrowing_readiness":
        blockers.append("phase_execution_state.active_candidate must be production_compat_exact_route_narrowing_readiness")
    if state.get("last_merged_pr") != "#766":
        blockers.append("phase_execution_state.last_merged_pr must record PR #766")
    if state.get("recommended_next_pr") != "phase_6i_external_enablement_and_compat_readiness_acceptance_bundle":
        blockers.append("phase_execution_state.recommended_next_pr must recommend Phase 6I")
    if state.get("next_allowed_actions") != []:
        blockers.append("phase_execution_state.next_allowed_actions must remain empty")

    changed = _changed_files()
    details["changed_files"] = sorted(changed)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"changed files outside Phase 6H allowlist: {unexpected}")
    forbidden = sorted(path for path in changed if path in FORBIDDEN_EXACT or path.startswith(FORBIDDEN_PREFIXES))
    if forbidden:
        blockers.append(f"changed forbidden runtime/protected files: {forbidden}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "details": details}


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = ["# Phase 6H Production Compat Exact-Route Narrowing Readiness Check", "", f"- overall: {report['overall']}", "- blockers:"]
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
