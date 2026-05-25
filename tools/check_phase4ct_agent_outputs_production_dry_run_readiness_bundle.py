#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4ct_agent_outputs_production_dry_run_readiness_bundle.md"
PLAN_YAML = ROOT / "docs/development/phase_4ct_agent_outputs_production_dry_run_readiness_bundle.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
RUNNER = ROOT / "tools/run_phase4ct_agent_outputs_production_readonly_dry_run.py"
TEST = ROOT / "tests/test_phase4ct_agent_outputs_production_dry_run_readiness_bundle.py"
AGENT_OUTPUTS = "/api/admin/automation-conversion/agent-outputs*"
AGGREGATE = "phase_4_internal_write_aggregate"
COMPLETED_STEP = "phase_4ct_agent_outputs_production_dry_run_readiness_completed"
NEXT_BUNDLE = "phase_4cu_phase4_internal_write_acceptance_review"
REQUIRED_ENV = {
    "AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED",
    "AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED",
    "AICRM_AGENT_OUTPUTS_REPO_BACKEND",
    "AICRM_AGENT_OUTPUTS_READONLY_DRY_RUN_DATABASE_URL",
}
REQUIRED_ARGS = {"--read-only", "--confirm-no-writes"}
FORBIDDEN_FALLBACKS = {"DATABASE_URL", "test_database_url", "staging_database_url", "fixture", "local_contract", "demo"}
REQUIRED_CHANGED = {
    "docs/development/phase_4ct_agent_outputs_production_dry_run_readiness_bundle.md",
    "docs/development/phase_4ct_agent_outputs_production_dry_run_readiness_bundle.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4ct_agent_outputs_production_dry_run_readiness_bundle.py",
    "tools/run_phase4ct_agent_outputs_production_readonly_dry_run.py",
    "tests/test_phase4ct_agent_outputs_production_dry_run_readiness_bundle.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "nginx/", "systemd/")
FORBIDDEN_EXACT = {"aicrm_next/main.py", "aicrm_next/production_compat/api.py", "app.py", "legacy_flask_app.py"}
FORBIDDEN_DOC_CLAIMS = {
    "production approved",
    "canary approved",
    "delete_ready: true",
    "delete_ready true",
    "production owner switched",
    "fallback removed",
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


def _check_runner_static(runner_text: str, blockers: list[str]) -> None:
    for snippet in (
        "--output-json",
        "--output-md",
        "not_executed_missing_approval",
        "not_executed_config_not_reviewed",
        "not_executed_missing_database_url",
        "agent_execution_triggered",
        "workflow_execution_triggered",
        "outbound_send_triggered",
        "llm_call_triggered",
        "raw_payload_exported",
        "file_download_triggered",
    ):
        if snippet not in runner_text:
            blockers.append(f"runner must support/report {snippet}")
    for env_name in REQUIRED_ENV:
        if env_name not in runner_text:
            blockers.append(f"runner must reference {env_name}")
    forbidden_fragments = (
        'os.environ.get("DATABASE_URL"',
        'os.getenv("DATABASE_URL"',
        "AICRM_AGENT_OUTPUTS_TEST_DATABASE_URL",
        "AICRM_AGENT_OUTPUTS_STAGING_DATABASE_URL",
        "wecom_ability_service",
        "DeepSeek",
        "deepseek",
        "LLM",
        "OpenClaw",
        "openclaw",
        "MCP",
        ".create_agent_output(",
        ".update_agent_output(",
        ".delete_agent_output(",
        ".start_agent_run(",
        ".dispatch_agent_run(",
        ".execute_agent_run(",
        ".run_due(",
        ".execute(",
        ".send(",
        ".replay(",
        ".export(",
        ".download(",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
    )
    for fragment in forbidden_fragments:
        if fragment in runner_text:
            blockers.append(f"runner contains forbidden fragment: {fragment}")
    for pattern in (r"\bexecute_agent_run\b", r"\bstart_agent_run\b", r"\bdispatch_agent_run\b"):
        if re.search(pattern, runner_text):
            blockers.append(f"runner contains forbidden agent-run call pattern: {pattern}")


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

    if data.get("status") != "phase_4ct_agent_outputs_production_readonly_dry_run_readiness":
        blockers.append("status must be phase_4ct_agent_outputs_production_readonly_dry_run_readiness")
    if data.get("bundle_type") != "production_readonly_dry_run_readiness_bundle":
        blockers.append("bundle_type must be production_readonly_dry_run_readiness_bundle")
    if data.get("route_family") != AGENT_OUTPUTS:
        blockers.append("route_family must be /api/admin/automation-conversion/agent-outputs*")
    if data.get("capability_owner") != "aicrm_next.automation_engine":
        blockers.append("capability_owner must be aicrm_next.automation_engine")

    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for key, value in sorted(authorizations.items()):
        if value is not False:
            blockers.append(f"authorizations.{key} must be false")
    expected_authorizations = {
        "production_owner_switch_authorized",
        "production_write_authorized",
        "production_repository_route_enablement_authorized",
        "production_compat_change_authorized",
        "fallback_removal_authorized",
        "real_external_call_authorized",
        "timer_execution_authorized",
        "automation_execution_authorized",
        "workflow_execution_authorized",
        "task_execution_authorized",
        "agent_execution_authorized",
        "outbound_send_authorized",
        "output_export_authorized",
        "file_download_authorized",
        "llm_deepseek_openclaw_mcp_authorized",
        "destructive_migration_authorized",
        "canary_approved",
        "delete_ready",
    }
    if set(authorizations) != expected_authorizations:
        blockers.append("authorizations keys must match the Phase 4CT safety contract")

    runner = data.get("runner") if isinstance(data.get("runner"), dict) else {}
    if runner.get("path") != "tools/run_phase4ct_agent_outputs_production_readonly_dry_run.py":
        blockers.append("runner.path is incorrect")
    if runner.get("default_result") != "blocked_evidence":
        blockers.append("runner.default_result must be blocked_evidence")
    if set(runner.get("required_env") or []) != REQUIRED_ENV:
        blockers.append("runner.required_env must contain the Phase 4CT approval/config/backend/DB envs")
    if set(runner.get("required_args") or []) != REQUIRED_ARGS:
        blockers.append("runner.required_args must require read-only and no-write confirmation")
    if set(runner.get("forbidden_fallbacks") or []) != FORBIDDEN_FALLBACKS:
        blockers.append("runner.forbidden_fallbacks must forbid shared/test/staging/fixture/local/demo fallback")

    read_only_scope = data.get("read_only_scope") if isinstance(data.get("read_only_scope"), dict) else {}
    if set(read_only_scope.get("allowed") or []) != {"shape_summary", "count_summary", "redacted_field_presence_summary"}:
        blockers.append("read_only_scope.allowed must be limited to shape/count/redacted field presence")
    forbidden_scope = set(read_only_scope.get("forbidden") or [])
    for item in (
        "create",
        "update",
        "delete",
        "run_due",
        "agent_run_execution",
        "replay",
        "task_execution",
        "workflow_execution",
        "timer_execution",
        "outbound_send",
        "external_call",
        "llm_call",
        "deepseek_call",
        "openclaw_call",
        "mcp_call",
        "raw_payload_export",
        "pii_export",
        "output_export",
        "file_download",
    ):
        if item not in forbidden_scope:
            blockers.append(f"read_only_scope.forbidden missing {item}")

    business = data.get("business_continuity") if isinstance(data.get("business_continuity"), dict) else {}
    for field in ("production_owner_unchanged", "legacy_fallback_retained", "production_compat_unchanged", "no_live_behavior_change"):
        if business.get(field) is not True:
            blockers.append(f"business_continuity.{field} must be true")
    next_bundle = data.get("next_bundle") if isinstance(data.get("next_bundle"), dict) else {}
    if next_bundle.get("recommended_next_step") != NEXT_BUNDLE or next_bundle.get("route_family") != AGGREGATE:
        blockers.append("next_bundle must point to Phase 4 aggregate acceptance review")

    _check_runner_static(runner_text, blockers)

    if state.get("last_merged_pr") != "#708":
        blockers.append("phase state last_merged_pr must record #708")
    if state.get("last_attempted_action") != "phase_4ct_agent_outputs_production_dry_run_readiness_bundle":
        blockers.append("phase state last_attempted_action must be Phase 4CT")
    if state.get("last_created_pr") != "#709":
        blockers.append("phase state last_created_pr must be #709")
    if state.get("active_candidate") != AGGREGATE:
        blockers.append("phase state active_candidate must advance to aggregate acceptance review")
    if state.get("recommended_next_pr") != NEXT_BUNDLE or set(state.get("next_allowed_actions") or []) != {NEXT_BUNDLE}:
        blockers.append("phase state next action must advance to Phase 4CU aggregate acceptance review")
    if COMPLETED_STEP not in set(state.get("completed_steps") or []):
        blockers.append("completed_steps must include Phase 4CT")
    dry_run_slices = state.get("production_dry_run_readiness_slices") if isinstance(state.get("production_dry_run_readiness_slices"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == AGENT_OUTPUTS
        and item.get("slice") == "agent_outputs_production_readonly_dry_run_readiness"
        and item.get("scope") == "blocked_by_default_readonly_dry_run_evidence"
        for item in dry_run_slices
    ):
        blockers.append("production_dry_run_readiness_slices must record agent-outputs readonly dry-run readiness")
    readiness = state.get("agent_outputs_readiness") if isinstance(state.get("agent_outputs_readiness"), dict) else {}
    for field in (
        "production_dry_run_readiness_bundle_completed",
        "production_readonly_dry_run_runner_completed",
        "production_readonly_evidence_gate_completed",
        "production_readonly_blocked_evidence_output_completed",
    ):
        if readiness.get(field) is not True:
            blockers.append(f"agent_outputs_readiness.{field} must be true")
    for field in (
        "production_readonly_dry_run_executed",
        "production_readonly_db_connection_attempted_by_default",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if readiness.get(field) is not False:
            blockers.append(f"agent_outputs_readiness.{field} must be false")
    if readiness.get("production_readonly_db_url_flag") != "AICRM_AGENT_OUTPUTS_READONLY_DRY_RUN_DATABASE_URL":
        blockers.append("agent_outputs_readiness.production_readonly_db_url_flag must be AICRM_AGENT_OUTPUTS_READONLY_DRY_RUN_DATABASE_URL")
    if readiness.get("production_readonly_approval_flag") != "AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED":
        blockers.append("agent_outputs_readiness.production_readonly_approval_flag must be AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED")
    if readiness.get("production_readonly_config_review_flag") != "AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED":
        blockers.append("agent_outputs_readiness.production_readonly_config_review_flag must be AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED")

    for phrase in FORBIDDEN_DOC_CLAIMS:
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(changed - REQUIRED_CHANGED)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4CT: {unexpected}")
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
        "details": {"changed_files": sorted(changed), "bundle_type": data.get("bundle_type"), "route_family": AGENT_OUTPUTS},
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4CT Agent Outputs Production Dry-Run Readiness Bundle Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- autopilot_deliverable: {str(report['autopilot_deliverable']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
            "",
            "## Warnings",
            *(f"- {item}" for item in report["warnings"]),
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
