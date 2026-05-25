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

DOC = ROOT / "docs/development/phase_4bu_tasks_fixture_runtime.md"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
API = ROOT / "aicrm_next/automation_engine/api.py"
APP = ROOT / "aicrm_next/automation_engine/application.py"
DTO = ROOT / "aicrm_next/automation_engine/dto.py"
REPO = ROOT / "aicrm_next/automation_engine/repo.py"
DOMAIN = ROOT / "aicrm_next/automation_engine/tasks.py"
TEST = ROOT / "tests/test_phase4bu_tasks_fixture_runtime.py"

TASKS = "/api/admin/automation-conversion/tasks*"
AGENTS = "/api/admin/automation-conversion/agents*"
REQUIRED_CHANGED = {
    "aicrm_next/automation_engine/api.py",
    "aicrm_next/automation_engine/application.py",
    "aicrm_next/automation_engine/dto.py",
    "aicrm_next/automation_engine/repo.py",
    "aicrm_next/automation_engine/tasks.py",
    "docs/development/phase_4bu_tasks_fixture_runtime.md",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4bu_tasks_fixture_runtime.py",
    "tools/check_automerge_eligibility.py",
    "tools/check_autonomous_development_loop.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4bu_tasks_fixture_runtime.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
ALLOWED_CHANGED = REQUIRED_CHANGED
FORBIDDEN_PATH_PREFIXES = ("aicrm_next/production_compat/", "wecom_ability_service/", "migrations/", "deploy/", "systemd/", "nginx/")
FORBIDDEN_EXACT = {"app.py", "legacy_flask_app.py", "aicrm_next/main.py"}
FORBIDDEN_DOC_CLAIMS = {
    "production_ready",
    "delete_ready true",
    "delete_ready: true",
    "canary_approved",
    "canary approved",
    "route_switch_ready=true",
}
REQUIRED_RUNTIME_TERMS = {
    API: [
        "list_tasks",
        "create_task",
        '"/api/admin/automation-conversion/tasks"',
    ],
    APP: [
        "ListTasksQuery",
        "CreateTaskCommand",
        "_task_production_unavailable_payload",
    ],
    DTO: [
        "TaskListRequest",
        "TaskCreateRequest",
    ],
    REPO: [
        "list_tasks",
        "create_task",
        "list_task_audit_events",
        "phase4bc_followup_task",
        "phase4bc_review_task",
    ],
    DOMAIN: [
        "normalize_task_create_payload",
        "task_projection",
        "task_side_effect_safety",
        "reject_dangerous_task_fields",
    ],
    TEST: [
        "test_fixture_repository_lists_seeded_tasks",
        "test_api_blocks_fixture_success_in_production_when_fastapi_available",
    ],
}


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
    ok, stdout, stderr = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    else:
        warnings.append(f"git ls-files --others unavailable: {(stderr or stdout).strip()}")
    return changed, warnings


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    for path in (DOC, STATE, API, APP, DTO, REPO, DOMAIN, TEST):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": {}}

    for path, terms in REQUIRED_RUNTIME_TERMS.items():
        text = _text(path)
        for term in terms:
            if term not in text:
                blockers.append(f"{path.relative_to(ROOT)} missing runtime term: {term}")

    state = load_yaml(STATE)
    if state.get("active_candidate") != AGENTS:
        blockers.append("phase_execution_state.active_candidate must advance to agents after tasks runtime slice")
    if state.get("last_merged_pr") != "#679":
        blockers.append("phase_execution_state.last_merged_pr must record #679")
    if state.get("last_attempted_action") != "phase_4bu_tasks_fixture_native_list_create_runtime":
        blockers.append("phase_execution_state.last_attempted_action must be Phase 4BU tasks runtime")
    if state.get("last_created_pr") != "#680":
        blockers.append("phase_execution_state.last_created_pr must be #680")
    if state.get("recommended_next_pr") != "phase_4bv_agents_fixture_native_list_create_runtime":
        blockers.append("phase_execution_state.recommended_next_pr must advance to agents fixture runtime")
    if set(state.get("next_allowed_actions") or []) != {"phase_4bv_agents_fixture_native_list_create_runtime"}:
        blockers.append("phase_execution_state.next_allowed_actions must be Phase 4BV agents runtime")
    if "phase_4bu_tasks_fixture_native_list_create_runtime_completed" not in set(state.get("completed_steps") or []):
        blockers.append("completed_steps must include Phase 4BU tasks runtime")

    readiness = state.get("tasks_readiness") if isinstance(state.get("tasks_readiness"), dict) else {}
    for field in (
        "metadata_planning_completed",
        "schema_route_surface_confirmed",
        "fixture_native_contract_planning_completed",
        "fixture_native_list_create_runtime_completed",
        "production_guard_blocks_fixture_success",
        "run_due_excluded",
        "task_execution_excluded",
        "workflow_execution_excluded",
        "timer_execution_excluded",
        "outbound_send_excluded",
    ):
        if readiness.get(field) is not True:
            blockers.append(f"tasks_readiness.{field} must be true")
    if set(readiness.get("implemented_runtime_slices") or []) != {
        "tasks_fixture_local_list",
        "tasks_fixture_local_metadata_create",
    }:
        blockers.append("tasks_readiness.implemented_runtime_slices must include list/create")
    for field in (
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
        "paused",
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if readiness.get(field) is not False:
            blockers.append(f"tasks_readiness.{field} must be false")

    doc_text = _text(DOC).lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")
    for required in (
        "Production owner unchanged",
        "Legacy fallback retained",
        "No production write by default",
        "No external calls by default",
        "Production must not return fixture fake success",
    ):
        if required not in _text(DOC):
            blockers.append(f"doc missing required implementation safety statement: {required}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4BU tasks package: {unexpected}")
    protected = sorted(path for path in changed if path in FORBIDDEN_EXACT or any(path.startswith(prefix) for prefix in FORBIDDEN_PATH_PREFIXES))
    if protected:
        blockers.append(f"forbidden protected files changed: {protected}")
    if not REQUIRED_CHANGED <= changed:
        blockers.append(f"expected changed files missing from diff: {sorted(REQUIRED_CHANGED - changed)}")

    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "autopilot_deliverable": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "details": {
            "route_family": TASKS,
            "next_route_family": AGENTS,
            "runtime_slice": "fixture_local_list_create",
            "changed_files": sorted(changed),
        },
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4BU Tasks Fixture Runtime Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- autopilot_deliverable: {str(report['autopilot_deliverable']).lower()}",
            f"- route_family: {report['details'].get('route_family')}",
            f"- runtime_slice: {report['details'].get('runtime_slice')}",
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
    print(
        json.dumps(
            {
                "overall": report["overall"],
                "ok": report["ok"],
                "autopilot_deliverable": report["autopilot_deliverable"],
                "blockers": report["blockers"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
