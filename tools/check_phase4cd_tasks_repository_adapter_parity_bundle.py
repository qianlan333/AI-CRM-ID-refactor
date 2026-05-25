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

DOC = ROOT / "docs/development/phase_4cd_tasks_repository_adapter_parity_bundle.md"
PLAN_YAML = ROOT / "docs/development/phase_4cd_tasks_repository_adapter_parity_bundle.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
REPO = ROOT / "aicrm_next/automation_engine/repo.py"
ADAPTER = ROOT / "aicrm_next/automation_engine/task_sqlalchemy_repository.py"
HARNESS = ROOT / "tools/run_phase4cd_tasks_adapter_parity.py"
TEST = ROOT / "tests/test_phase4cd_tasks_repository_adapter_parity_bundle.py"

TASKS = "/api/admin/automation-conversion/tasks*"
AGENTS = "/api/admin/automation-conversion/agents*"
NEXT_BUNDLE = "phase_4ce_agents_repository_adapter_parity_bundle"
COMPLETED_STEP = "phase_4cd_tasks_repository_adapter_parity_completed"
REQUIRED_CHANGED = {
    "aicrm_next/automation_engine/repo.py",
    "aicrm_next/automation_engine/task_sqlalchemy_repository.py",
    "docs/development/phase_4cd_tasks_repository_adapter_parity_bundle.md",
    "docs/development/phase_4cd_tasks_repository_adapter_parity_bundle.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4cd_tasks_repository_adapter_parity_bundle.py",
    "tools/run_phase4cd_tasks_adapter_parity.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4cd_tasks_repository_adapter_parity_bundle.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
FORBIDDEN_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "systemd/", "nginx/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py", "aicrm_next/main.py"}
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


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, REPO, ADAPTER, HARNESS, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": {}}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    doc_text = DOC.read_text(encoding="utf-8").lower()
    adapter_text = ADAPTER.read_text(encoding="utf-8")
    repo_text = REPO.read_text(encoding="utf-8")
    harness_text = HARNESS.read_text(encoding="utf-8")

    bundle = data.get("bundle") if isinstance(data.get("bundle"), dict) else {}
    if data.get("status") != "phase_4cd_tasks_repository_adapter_parity_bundle":
        blockers.append("status must be Phase 4CD tasks repository adapter parity bundle")
    if bundle.get("type") != "repository_adapter_parity_bundle" or bundle.get("route_family") != TASKS:
        blockers.append("bundle must be repository_adapter_parity_bundle for tasks")
    if int(bundle.get("estimated_pr_count_reduction_percent") or 0) < 40:
        blockers.append("bundle must estimate at least 40 percent PR count reduction")

    adapter = data.get("adapter") if isinstance(data.get("adapter"), dict) else {}
    if adapter.get("backend_flag") != "AICRM_TASKS_REPO_BACKEND":
        blockers.append("adapter backend flag must be route-specific")
    if set(adapter.get("database_url_flags") or []) != {"AICRM_TASKS_TEST_DATABASE_URL", "AICRM_TASKS_STAGING_DATABASE_URL"}:
        blockers.append("adapter database URL flags must be route-specific test/staging only")
    if "DATABASE_URL" not in set(adapter.get("forbidden_database_url_fallbacks") or []):
        blockers.append("adapter must forbid DATABASE_URL fallback")
    if adapter.get("default_backend_remains_fixture_local") is not True:
        blockers.append("default backend must remain fixture/local")
    if adapter.get("production_route_owner_enabled") is not False or adapter.get("production_write_authorized") is not False:
        blockers.append("adapter must not enable production owner or production write")

    safety = data.get("safety") if isinstance(data.get("safety"), dict) else {}
    for field in ("no_database_url_fallback", "route_specific_test_db_required", "refuse_production_looking_urls", "default_backend_fixture_local"):
        if safety.get(field) is not True:
            blockers.append(f"safety.{field} must be true")
    for field in (
        "production_owner_switch_authorized",
        "production_repository_route_enablement_authorized",
        "production_write_authorized",
        "fallback_removal_authorized",
        "destructive_migration_authorized",
        "real_external_call_authorized",
        "run_due_authorized",
        "task_execution_authorized",
        "workflow_execution_authorized",
        "timer_execution_authorized",
        "outbound_send_authorized",
        "delete_ready",
    ):
        if safety.get(field) is not False:
            blockers.append(f"safety.{field} must be false")

    if "SqlAlchemyTaskRepository" not in adapter_text:
        blockers.append("adapter must define SqlAlchemyTaskRepository")
    if "automation_tasks" not in adapter_text or "automation_task_idempotency" not in adapter_text or "automation_task_audit_log" not in adapter_text:
        blockers.append("adapter must cover task main/idempotency/audit tables")
    if "TASK_TEST_DATABASE_URL_ENV" not in repo_text or "TASK_STAGING_DATABASE_URL_ENV" not in repo_text:
        blockers.append("repo must expose route-specific task DB URL flags")
    if 'os.getenv("DATABASE_URL"' in repo_text or 'os.environ.get("DATABASE_URL"' in repo_text:
        blockers.append("repo must not fall back to DATABASE_URL")
    if 'os.getenv("DATABASE_URL"' in harness_text or 'os.environ.get("DATABASE_URL"' in harness_text:
        blockers.append("harness must not fall back to DATABASE_URL")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state.get("active_candidate") != AGENTS or state_update.get("active_candidate") != AGENTS:
        blockers.append("phase state must advance active candidate to agents")
    if state.get("last_merged_pr") != "#688":
        blockers.append("phase state last_merged_pr must record #688")
    if state.get("last_attempted_action") != "phase_4cd_tasks_repository_adapter_parity_bundle":
        blockers.append("phase state last_attempted_action must be Phase 4CD")
    if state.get("last_created_pr") != "#689":
        blockers.append("phase state last_created_pr must be #689")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append("phase state recommended_next_pr must be Phase 4CE")
    if set(state.get("next_allowed_actions") or []) != {NEXT_BUNDLE}:
        blockers.append("phase state next_allowed_actions must be Phase 4CE")
    if COMPLETED_STEP not in set(state.get("completed_steps") or []):
        blockers.append("completed_steps must include Phase 4CD")
    readiness = state.get("tasks_readiness") if isinstance(state.get("tasks_readiness"), dict) else {}
    for field in ("repository_adapter_parity_completed", "no_database_url_fallback", "default_backend_fixture_local", "test_db_parity_harness_completed", "idempotency_audit_rollback_scaffold_completed"):
        if readiness.get(field) is not True:
            blockers.append(f"tasks_readiness.{field} must be true")
    for field in ("production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if readiness.get(field) is not False:
            blockers.append(f"tasks_readiness.{field} must be false")

    for phrase in FORBIDDEN_CLAIMS:
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(changed - REQUIRED_CHANGED)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4CD: {unexpected}")
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
        "details": {"changed_files": sorted(changed), "bundle_type": bundle.get("type"), "route_family": TASKS},
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4CD Tasks Repository Adapter Parity Bundle Check",
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
