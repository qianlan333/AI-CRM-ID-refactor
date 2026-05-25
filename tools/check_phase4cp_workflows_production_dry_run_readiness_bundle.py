#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4cp_workflows_production_dry_run_readiness_bundle.md"
PLAN_YAML = ROOT / "docs/development/phase_4cp_workflows_production_dry_run_readiness_bundle.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
RUNNER = ROOT / "tools/run_phase4cp_workflows_production_readonly_dry_run.py"
TEST = ROOT / "tests/test_phase4cp_workflows_production_dry_run_readiness_bundle.py"
WORKFLOWS = "/api/admin/automation-conversion/workflows*"
WORKFLOW_NODES = "/api/admin/automation-conversion/workflow-nodes*"
COMPLETED_STEP = "phase_4cp_workflows_production_dry_run_readiness_completed"
NEXT_BUNDLE = "phase_4cq_workflow_nodes_production_dry_run_readiness_bundle"
REQUIRED_CHANGED = {
    "docs/development/phase_4cp_workflows_production_dry_run_readiness_bundle.md",
    "docs/development/phase_4cp_workflows_production_dry_run_readiness_bundle.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4cp_workflows_production_dry_run_readiness_bundle.py",
    "tools/run_phase4cp_workflows_production_readonly_dry_run.py",
    "tests/test_phase4cp_workflows_production_dry_run_readiness_bundle.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "systemd/", "nginx/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py"}
FORBIDDEN_CLAIMS = {
    "production repository enabled as route owner",
    "route switch authorized",
    "fallback removal authorized",
    "production approved",
    "canary approved",
    "delete_ready true",
}


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ModuleNotFoundError:
        if str(ROOT) not in sys.path:
            sys.path[:0] = [str(ROOT)]
        from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml as fallback

        return fallback(path)


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only"], ["diff", "--name-only", "--cached"]):
        ok, stdout, stderr = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
        else:
            warnings.append(f"git {' '.join(args)} unavailable: {(stderr or stdout).strip()}")
    ok, stdout, _ = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    return changed, warnings


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, RUNNER, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": {}}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()
    runner_text = RUNNER.read_text(encoding="utf-8")
    bundle = data.get("bundle") if isinstance(data.get("bundle"), dict) else {}
    runtime = data.get("runtime_behavior") if isinstance(data.get("runtime_behavior"), dict) else {}
    safety = data.get("safety") if isinstance(data.get("safety"), dict) else {}

    if data.get("status") != "phase_4cp_workflows_production_dry_run_readiness_bundle":
        blockers.append("status must be Phase 4CP workflows production dry-run readiness bundle")
    if bundle.get("type") != "production_read_only_dry_run_readiness_bundle" or bundle.get("route_family") != WORKFLOWS:
        blockers.append("bundle must be production_read_only_dry_run_readiness_bundle for workflows")
    if int(bundle.get("estimated_pr_count_reduction_percent") or 0) < 40:
        blockers.append("bundle must estimate at least 40 percent PR count reduction")
    if runtime.get("runner_path") != "tools/run_phase4cp_workflows_production_readonly_dry_run.py":
        blockers.append("runtime runner path is incorrect")
    for flag in (
        "AICRM_PHASE4CP_PRODUCTION_READONLY_DRY_RUN_APPROVED=1",
        "AICRM_PHASE4CP_PRODUCTION_CONFIG_REVIEWED=1",
        "AICRM_WORKFLOWS_REPO_BACKEND=sqlalchemy",
        "AICRM_WORKFLOWS_READONLY_DRY_RUN_DATABASE_URL",
        "--read-only",
        "--confirm-no-writes",
    ):
        if flag not in set(runtime.get("read_only_execution_requires") or []):
            blockers.append(f"runtime gate missing {flag}")
    for field in ("database_url_fallback_used", "test_or_staging_db_fallback_used", "raw_payload_exported", "raw_pii_exported"):
        if runtime.get(field) is not False:
            blockers.append(f"runtime_behavior.{field} must be false")

    for field in ("no_database_url_fallback", "route_specific_readonly_dry_run_db_required", "default_backend_fixture_local"):
        if safety.get(field) is not True:
            blockers.append(f"safety.{field} must be true")
    for field in (
        "production_owner_switch_authorized",
        "production_repository_route_enablement_authorized",
        "production_write_authorized",
        "production_compat_change_authorized",
        "fallback_removal_authorized",
        "destructive_migration_authorized",
        "real_external_call_authorized",
        "timer_execution_authorized",
        "workflow_execution_authorized",
        "task_execution_authorized",
        "outbound_send_authorized",
        "canary_approval",
        "delete_ready",
    ):
        if safety.get(field) is not False:
            blockers.append(f"safety.{field} must be false")

    forbidden_runner_fragments = (
        'os.environ.get("DATABASE_URL"',
        'os.getenv("DATABASE_URL"',
        'AICRM_WORKFLOWS_TEST_DATABASE_URL',
        'AICRM_WORKFLOWS_STAGING_DATABASE_URL',
        ".create_workflow(",
    )
    for fragment in forbidden_runner_fragments:
        if fragment in runner_text:
            blockers.append(f"runner contains forbidden fragment: {fragment}")
    for snippet in ("not_executed_missing_approval", "not_executed_missing_dry_run_db", "read_only_dry_run_executed", "db_connection_attempted"):
        if snippet not in runner_text:
            blockers.append(f"runner must report {snippet}")

    if state.get("last_merged_pr") != "#704":
        blockers.append("phase state last_merged_pr must record #704")
    if state.get("last_attempted_action") != "phase_4cp_workflows_production_dry_run_readiness_bundle":
        blockers.append("phase state last_attempted_action must be Phase 4CP")
    if state.get("last_created_pr") != "#705":
        blockers.append("phase state last_created_pr must be #705")
    if state.get("active_candidate") != WORKFLOW_NODES:
        blockers.append("phase state active_candidate must advance to workflow-nodes")
    if state.get("recommended_next_pr") != NEXT_BUNDLE or set(state.get("next_allowed_actions") or []) != {NEXT_BUNDLE}:
        blockers.append("phase state next action must advance to Phase 4CQ workflow-nodes production dry-run readiness")
    if COMPLETED_STEP not in set(state.get("completed_steps") or []):
        blockers.append("completed_steps must include Phase 4CP")
    dry_run_slices = state.get("production_dry_run_readiness_slices") if isinstance(state.get("production_dry_run_readiness_slices"), list) else []
    if not any(isinstance(item, dict) and item.get("route_family") == WORKFLOWS and item.get("slice") == "workflows_production_readonly_dry_run_readiness" for item in dry_run_slices):
        blockers.append("production_dry_run_readiness_slices must record workflows readiness")
    workflows = state.get("workflows_readiness") if isinstance(state.get("workflows_readiness"), dict) else {}
    for field in ("production_dry_run_readiness_bundle_completed", "production_readonly_dry_run_runner_completed", "production_readonly_evidence_gate_completed", "production_readonly_blocked_evidence_output_completed"):
        if workflows.get(field) is not True:
            blockers.append(f"workflows_readiness.{field} must be true")
    if workflows.get("production_readonly_dry_run_executed") is not False:
        blockers.append("workflows_readiness.production_readonly_dry_run_executed must be false")
    if workflows.get("production_readonly_db_url_flag") != "AICRM_WORKFLOWS_READONLY_DRY_RUN_DATABASE_URL":
        blockers.append("workflows_readiness production readonly DB flag mismatch")
    for field in ("production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if workflows.get(field) is not False:
            blockers.append(f"workflows_readiness.{field} must be false")

    for phrase in FORBIDDEN_CLAIMS:
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(changed - REQUIRED_CHANGED)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4CP: {unexpected}")
    missing = sorted(REQUIRED_CHANGED - changed)
    if missing:
        blockers.append(f"required changed files missing from diff: {missing}")
    protected = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES))
    if protected:
        blockers.append(f"forbidden protected files changed: {protected}")

    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "autopilot_deliverable": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "details": {"changed_files": sorted(changed), "bundle_type": bundle.get("type"), "route_family": WORKFLOWS},
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4CP Workflows Production Dry-Run Readiness Bundle Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- autopilot_deliverable: {str(report['autopilot_deliverable']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = build_report()
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
