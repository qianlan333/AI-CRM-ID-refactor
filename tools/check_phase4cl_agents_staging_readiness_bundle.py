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

from tools.check_phase4bh_agents_fixture_native_implementation_owner_decision import load_yaml


DOC = ROOT / "docs/development/phase_4cl_agents_staging_readiness_bundle.md"
PLAN_YAML = ROOT / "docs/development/phase_4cl_agents_staging_readiness_bundle.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
RUNNER = ROOT / "tools/run_phase4cl_agents_staging_readiness.py"
TEST = ROOT / "tests/test_phase4cl_agents_staging_readiness_bundle.py"

AGENTS = "/api/admin/automation-conversion/agents*"
AGENT_OUTPUTS = "/api/admin/automation-conversion/agent-outputs*"
NEXT_BUNDLE = "phase_4cm_agent_outputs_staging_readiness_bundle"
COMPLETED_STEP = "phase_4cl_agents_staging_readiness_completed"
REQUIRED_CHANGED = {
    "docs/development/phase_4cl_agents_staging_readiness_bundle.md",
    "docs/development/phase_4cl_agents_staging_readiness_bundle.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4cl_agents_staging_readiness_bundle.py",
    "tools/run_phase4cl_agents_staging_readiness.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4cl_agents_staging_readiness_bundle.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "systemd/", "nginx/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py"}
FORBIDDEN_CLAIMS = {"production_ready", "delete_ready true", "delete_ready: true", "canary_approved", "canary approved", "route_switch_ready=true"}


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


def _contains_forbidden_env_fallback(text: str) -> bool:
    return any(
        fragment in text
        for fragment in (
            'os.getenv("DATABASE_URL"',
            'os.environ.get("DATABASE_URL"',
            'os.getenv("AICRM_AGENTS_TEST_DATABASE_URL"',
            'os.environ.get("AICRM_AGENTS_TEST_DATABASE_URL"',
        )
    )


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
    if data.get("status") != "phase_4cl_agents_staging_readiness_bundle":
        blockers.append("status must be Phase 4CL agents staging readiness bundle")
    if bundle.get("type") != "staging_readiness_bundle" or bundle.get("route_family") != AGENTS:
        blockers.append("bundle must be staging_readiness_bundle for agents")
    if int(bundle.get("estimated_pr_count_reduction_percent") or 0) < 40:
        blockers.append("bundle must estimate at least 40 percent PR count reduction")

    readiness = data.get("staging_readiness") if isinstance(data.get("staging_readiness"), dict) else {}
    expected_flags = {
        "runner_path": "tools/run_phase4cl_agents_staging_readiness.py",
        "staging_database_url_flag": "AICRM_AGENTS_STAGING_DATABASE_URL",
        "backend_flag": "AICRM_AGENTS_REPO_BACKEND",
        "approval_flag": "AICRM_PHASE4CL_STAGING_SMOKE_APPROVED",
        "write_approval_flag": "AICRM_PHASE4CL_STAGING_WRITE_APPROVED",
    }
    for field, expected in expected_flags.items():
        if readiness.get(field) != expected:
            blockers.append(f"staging_readiness.{field} must be {expected}")
    if "DATABASE_URL" not in set(readiness.get("forbidden_database_url_fallbacks") or []):
        blockers.append("staging readiness must forbid DATABASE_URL fallback")
    if "AICRM_AGENTS_TEST_DATABASE_URL" not in set(readiness.get("forbidden_database_url_fallbacks") or []):
        blockers.append("staging readiness must forbid TEST_DATABASE_URL fallback")
    for field in ("db_connection_attempted_by_default", "staging_smoke_executed_by_default", "staging_write_executed_by_default"):
        if readiness.get(field) is not False:
            blockers.append(f"staging_readiness.{field} must default false")

    safety = data.get("safety") if isinstance(data.get("safety"), dict) else {}
    for field in ("no_database_url_fallback", "route_specific_staging_db_required", "refuse_production_looking_urls", "default_backend_fixture_local"):
        if safety.get(field) is not True:
            blockers.append(f"safety.{field} must be true")
    for field in (
        "production_owner_switch_authorized",
        "production_repository_route_enablement_authorized",
        "production_write_authorized",
        "fallback_removal_authorized",
        "destructive_migration_authorized",
        "real_external_call_authorized",
        "timer_execution_authorized",
        "workflow_execution_authorized",
        "task_execution_authorized",
        "agent_run_execution_authorized",
        "llm_generation_authorized",
        "deepseek_adapter_authorized",
        "openclaw_mcp_authorized",
        "outbound_send_authorized",
        "staging_write_smoke_authorized_by_default",
        "delete_ready",
    ):
        if safety.get(field) is not False:
            blockers.append(f"safety.{field} must be false")

    if _contains_forbidden_env_fallback(runner_text):
        blockers.append("runner must not fall back to DATABASE_URL or agents test DB URL")
    for snippet in ("db_connection_attempted", "staging_smoke_executed", "ready_for_staging_smoke_execution"):
        if snippet not in runner_text:
            blockers.append(f"runner must report {snippet}")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state.get("active_candidate") != AGENT_OUTPUTS or state_update.get("active_candidate") != AGENT_OUTPUTS:
        blockers.append("phase state must advance active candidate to agent-outputs staging readiness")
    if state.get("last_merged_pr") != "#697":
        blockers.append("phase state last_merged_pr must record #697")
    if state.get("last_attempted_action") != "phase_4cl_agents_staging_readiness_bundle":
        blockers.append("phase state last_attempted_action must be Phase 4CL")
    if state.get("last_created_pr") != "#698":
        blockers.append("phase state last_created_pr must be #698")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append("phase state recommended_next_pr must be Phase 4CM")
    if set(state.get("next_allowed_actions") or []) != {NEXT_BUNDLE}:
        blockers.append("phase state next_allowed_actions must be Phase 4CM")
    if COMPLETED_STEP not in set(state.get("completed_steps") or []):
        blockers.append("completed_steps must include Phase 4CL")

    top_level_staging = state.get("staging_readiness_slices") if isinstance(state.get("staging_readiness_slices"), list) else []
    if not any(isinstance(item, dict) and item.get("route_family") == AGENTS and item.get("slice") == "agents_staging_readiness_preflight" for item in top_level_staging):
        blockers.append("staging_readiness_slices must record agents staging readiness preflight")
    agents = state.get("agents_readiness") if isinstance(state.get("agents_readiness"), dict) else {}
    for field in (
        "staging_readiness_bundle_completed",
        "staging_readiness_preflight_completed",
        "staging_evidence_gate_completed",
        "staging_blocked_evidence_output_completed",
    ):
        if agents.get(field) is not True:
            blockers.append(f"agents_readiness.{field} must be true")
    if agents.get("staging_smoke_executed") is not False:
        blockers.append("agents_readiness.staging_smoke_executed must be false")
    for field in (
        "agent_run_execution_excluded",
        "llm_generation_excluded",
        "deepseek_adapter_excluded",
        "openclaw_mcp_excluded",
        "external_call_excluded",
    ):
        if agents.get(field) is not True:
            blockers.append(f"agents_readiness.{field} must remain true")
    for field in (
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if agents.get(field) is not False:
            blockers.append(f"agents_readiness.{field} must be false")

    for phrase in FORBIDDEN_CLAIMS:
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(changed - REQUIRED_CHANGED)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4CL: {unexpected}")
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
        "details": {"changed_files": sorted(changed), "bundle_type": bundle.get("type"), "route_family": AGENTS},
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4CL Agents Staging Readiness Bundle Check",
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
