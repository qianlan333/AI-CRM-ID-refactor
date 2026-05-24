#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

ROUTE = "/api/admin/automation-conversion/task-groups*"
REQUIRED_FIELDS = {"id", "program_id", "group_name", "sort_order", "created_by", "updated_by", "created_at", "updated_at", "archived_at"}
AUTH_FALSE_FIELDS = {
    "runtime_implementation_authorized",
    "staging_smoke_execution_authorized",
    "production_dry_run_execution_authorized",
    "production_data_connection_authorized",
    "production_write_authorized",
    "production_repository_route_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "timer_execution_authorized",
    "outbound_send_authorized",
    "canary_approval_authorized",
    "delete_ready",
}
SIDE_EFFECT_FALSE_FIELDS = {
    "real_external_call_allowed",
    "automation_execution_allowed",
    "outbound_send_allowed",
    "wecom_call_allowed",
    "openclaw_call_allowed",
    "mcp_call_allowed",
    "timer_execution_allowed",
    "production_data_allowed",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.md",
    "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4ap_task_groups_fixture_native_contract_plan.py",
    "tools/check_phase4ao_task_groups_schema_route_surface_confirmation.py",
    "tools/check_phase4an_task_groups_native_contract_plan.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4ap_task_groups_fixture_native_contract_plan.py",
    "tests/test_phase4ao_task_groups_schema_route_surface_confirmation.py",
    "tests/test_phase4an_task_groups_native_contract_plan.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
PROTECTED_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "systemd/", "nginx/")
PROTECTED_EXACT = {"app.py", "legacy_flask_app.py"}
FORBIDDEN_DOC_CLAIMS = {"production_ready", "delete_ready true", "delete_ready: true", "canary_approved", "canary approved", "route_switch_ready=true"}


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value == "[]":
        return []
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _strip_yaml_comments(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
    return line.rstrip()


def _yaml_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = _strip_yaml_comments(raw)
        if stripped.strip():
            lines.append((len(stripped) - len(stripped.lstrip(" ")), stripped.strip()))
    return lines


def _parse_yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, current_text = lines[index]
    if current_indent < indent:
        return {}, index
    if current_text.startswith("- "):
        result: list[Any] = []
        while index < len(lines):
            line_indent, text = lines[index]
            if line_indent != indent or not text.startswith("- "):
                break
            item_text = text[2:].strip()
            index += 1
            if not item_text:
                value, index = _parse_yaml_block(lines, index, indent + 2)
                result.append(value)
                continue
            if ":" not in item_text:
                result.append(_parse_scalar(item_text))
                continue
            key, raw_value = item_text.split(":", 1)
            item: dict[str, Any] = {}
            raw_value = raw_value.strip()
            if raw_value:
                item[key.strip()] = _parse_scalar(raw_value)
            else:
                value, index = _parse_yaml_block(lines, index, indent + 2)
                item[key.strip()] = value
            while index < len(lines) and lines[index][0] > indent:
                nested_value, index = _parse_yaml_block(lines, index, indent + 2)
                if isinstance(nested_value, dict):
                    item.update(nested_value)
            result.append(item)
        return result, index
    result: dict[str, Any] = {}
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent != indent or text.startswith("- "):
            break
        if ":" not in text:
            index += 1
            continue
        key, raw_value = text.split(":", 1)
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            result[key.strip()] = _parse_scalar(raw_value)
        else:
            value, index = _parse_yaml_block(lines, index, indent + 2)
            result[key.strip()] = value
    return result, index


def load_yaml(path: Path = PLAN_YAML) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        data, _ = _parse_yaml_block(_yaml_lines(text), 0, 0)
        return data if isinstance(data, dict) else {}


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


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, MANIFEST, BACKLOG):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "warnings": warnings, "details": {}}

    data = load_yaml()
    state = load_yaml(STATE)
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    backlog_text = BACKLOG.read_text(encoding="utf-8")

    if data.get("status") != "phase_4ap_task_groups_fixture_native_contract_planning_no_runtime_change":
        blockers.append("status must be phase_4ap_task_groups_fixture_native_contract_planning_no_runtime_change")
    if data.get("route_family") != ROUTE:
        blockers.append("route_family must be task-groups wildcard")
    if ROUTE not in manifest_text or ROUTE not in backlog_text:
        blockers.append("task-groups route must exist in manifest and backlog")
    if data.get("current_runtime_owner") != "production_compat" or data.get("production_behavior") != "legacy_forward":
        blockers.append("production owner must remain production_compat legacy_forward")
    if data.get("legacy_fallback_retained") is not True or data.get("fixture_allowed_in_production") is not False:
        blockers.append("legacy fallback must be retained and fixture production use must be false")

    previous = data.get("previous_phase") if isinstance(data.get("previous_phase"), dict) else {}
    if previous.get("merged_pr") != "#646" or previous.get("completed") is not True:
        blockers.append("previous_phase must record Phase 4AO merged in #646")

    routes = data.get("planned_fixture_routes") or []
    route_scopes = {(item.get("method"), item.get("scope")) for item in routes if isinstance(item, dict)}
    if route_scopes != {("GET", "fixture_local_list"), ("POST", "fixture_local_metadata_create")}:
        blockers.append("planned_fixture_routes must be GET list and POST metadata create only")

    excluded_paths = {str(item.get("path")) for item in data.get("excluded_routes") or [] if isinstance(item, dict)}
    if not {"/api/admin/automation-conversion/tasks*", "/api/admin/automation-conversion/tasks/run-due"} <= excluded_paths:
        blockers.append("excluded_routes must include tasks family and run-due")

    seed = data.get("fixture_seed") if isinstance(data.get("fixture_seed"), dict) else {}
    if seed.get("deterministic") is not True or seed.get("production_data_allowed") is not False:
        blockers.append("fixture_seed must be deterministic and forbid production data")
    if not REQUIRED_FIELDS <= set(seed.get("required_fields") or []):
        blockers.append("fixture_seed.required_fields incomplete")

    list_contract = data.get("list_contract") if isinstance(data.get("list_contract"), dict) else {}
    if list_contract.get("archived_groups_excluded_by_default") is not True:
        blockers.append("list_contract must exclude archived groups by default")
    if not {"ok", "groups", "side_effect_safety"} <= set(list_contract.get("response_keys") or []):
        blockers.append("list_contract.response_keys incomplete")

    create_contract = data.get("create_contract") if isinstance(data.get("create_contract"), dict) else {}
    if not {"group_name", "idempotency_key"} <= set(create_contract.get("required_payload") or []):
        blockers.append("create_contract.required_payload must include group_name and idempotency_key")
    for field in ("missing_name_rejected", "duplicate_group_name_rejected", "dangerous_fields_rejected"):
        if create_contract.get(field) is not True:
            blockers.append(f"create_contract.{field} must be true")

    idempotency = data.get("idempotency") if isinstance(data.get("idempotency"), dict) else {}
    for field in ("route_family_scope_required", "operation_scope_required", "operator_scope_required", "idempotency_key_required", "replay_same_hash", "conflict_different_hash"):
        if idempotency.get(field) is not True:
            blockers.append(f"idempotency.{field} must be true")

    audit = data.get("audit") if isinstance(data.get("audit"), dict) else {}
    for field in ("audit_event_required", "after_snapshot_required", "rollback_payload_required", "side_effect_safety_required"):
        if audit.get(field) is not True:
            blockers.append(f"audit.{field} must be true")

    side_effect = data.get("side_effect_safety") if isinstance(data.get("side_effect_safety"), dict) else {}
    for field in SIDE_EFFECT_FALSE_FIELDS:
        if side_effect.get(field) is not False:
            blockers.append(f"side_effect_safety.{field} must be false")

    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    for field in ("active_candidate", "last_merged_pr", "last_attempted_action", "recommended_next_pr", "owner_approval_required"):
        if state.get(field) != state_update.get(field):
            blockers.append(f"phase_execution_state.{field} must match Phase 4AP plan")
    if state_update.get("phase_4ap_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4AP completed step")
    if set(state.get("next_allowed_actions") or []) != {"phase_4aq_task_groups_fixture_native_implementation_owner_decision"}:
        blockers.append("next_allowed_actions must advance to Phase 4AQ owner decision")
    readiness = state.get("task_groups_readiness") if isinstance(state.get("task_groups_readiness"), dict) else {}
    if readiness.get("fixture_native_contract_planning_completed") is not True:
        blockers.append("task_groups_readiness.fixture_native_contract_planning_completed must be true")
    if readiness.get("fixture_native_implementation_requires_owner_decision") is not True:
        blockers.append("task_groups_readiness.fixture_native_implementation_requires_owner_decision must be true")
    for field in ("production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if readiness.get(field) is not False:
            blockers.append(f"task_groups_readiness.{field} must be false")

    rec = data.get("phase_4aq_recommendation") if isinstance(data.get("phase_4aq_recommendation"), dict) else {}
    if rec.get("recommended_next_step") != "task_groups_fixture_native_implementation_owner_decision":
        blockers.append("phase_4aq_recommendation must recommend owner decision before runtime implementation")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4aq_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4AP package: {unexpected}")
    protected = sorted(path for path in changed if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "warnings": warnings, "details": {"changed_files": sorted(changed)}}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = ["# Phase 4AP Task Groups Fixture Native Contract Check", "", f"- overall: {report['overall']}", f"- ok: {str(report['ok']).lower()}", "", "## Blockers", *(f"- {item}" for item in report["blockers"]), "", "## Warnings", *(f"- {item}" for item in report["warnings"])]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = build_report()
    _write_outputs(report, args.output_json, args.output_md)
    print(f"overall: {report['overall']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
