#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/autonomous_development_loop.md"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STOP = ROOT / "docs/development/autonomous_stop_conditions.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

REQUIRED_STATE_FIELDS = {
    "version",
    "status",
    "autopilot",
    "current_phase",
    "active_candidate",
    "capability_owner",
    "last_merged_pr",
    "completed_steps",
    "next_allowed_actions",
    "forbidden_without_owner_approval",
    "action_templates_readiness",
    "paused_candidates",
    "task_groups_readiness",
    "work_package_policy",
}
ALLOWED_NEXT_ACTIONS = {
    "phase_4ao_task_groups_schema_route_surface_confirmation",
}
REQUIRED_COMPLETED_STEPS = {
    "phase_4al_staging_execution_readiness_gate_completed",
    "action_templates_staging_approval_config_closure_package_created",
    "action_templates_staging_owner_decision_package_created",
    "phase_4an_task_groups_native_contract_planning_completed",
}
REQUIRED_FORBIDDEN = {
    "production owner switch",
    "fallback removal",
    "production write",
    "real external call",
    "timer",
    "outbound send",
    "deploy config",
    "destructive migration",
    "delete_ready",
    "canary approval",
}
STOP_IDS = {
    "production_owner_switch",
    "fallback_removal",
    "production_write",
    "real_external_call",
    "timer_or_execution",
    "outbound_send",
    "deploy_config",
    "destructive_migration",
    "delete_ready",
    "canary_approval",
}
REQUIRED_WORK_PACKAGE_POLICY_TRUE = {
    "state_only_pr_requires_explanation",
    "avoid_repeated_blocked_evidence_review",
    "low_risk_admin_merge_allowed",
    "admin_merge_requires_eligible_true",
    "admin_merge_requires_required_checks_green",
}


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


def _load_yaml_without_dependency(path: Path) -> dict[str, Any]:
    data, _ = _parse_yaml_block(_yaml_lines(path.read_text(encoding="utf-8")), 0, 0)
    return data if isinstance(data, dict) else {}


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ModuleNotFoundError:
        return _load_yaml_without_dependency(path)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_strings(value: Any) -> set[str]:
    return {str(item).strip() for item in _as_list(value)}


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> set[str]:
    changed: set[str] = set()
    for args in (
        ["diff", "--name-only", "origin/main...HEAD"],
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        ok, stdout, _ = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    return changed


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    for path in (DOC, STATE, STOP, MANIFEST, BACKLOG):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")

    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "warnings": warnings, "details": details}

    state = load_yaml(STATE)
    stop = load_yaml(STOP)
    details["state"] = {
        "current_phase": state.get("current_phase"),
        "active_candidate": state.get("active_candidate"),
        "capability_owner": state.get("capability_owner"),
        "last_merged_pr": state.get("last_merged_pr"),
    }

    missing_state_fields = sorted(REQUIRED_STATE_FIELDS - set(state))
    if missing_state_fields:
        blockers.append(f"phase_execution_state missing fields: {missing_state_fields}")

    if state.get("current_phase") != "phase_4_internal_write":
        blockers.append("current_phase must be phase_4_internal_write")
    if state.get("active_candidate") != "/api/admin/automation-conversion/task-groups*":
        blockers.append("active_candidate must advance to /api/admin/automation-conversion/task-groups* after action-templates pause")
    if state.get("capability_owner") != "aicrm_next.automation_engine":
        blockers.append("capability_owner must be aicrm_next.automation_engine")
    if state.get("last_merged_pr") != "#644":
        blockers.append("last_merged_pr must record latest completed autopilot PR #644")

    completed = _as_strings(state.get("completed_steps"))
    missing_completed = sorted(REQUIRED_COMPLETED_STEPS - completed)
    if missing_completed:
        blockers.append(f"completed_steps missing required Phase 4AL asset: {missing_completed}")

    next_allowed = _as_strings(state.get("next_allowed_actions"))
    if next_allowed != ALLOWED_NEXT_ACTIONS:
        blockers.append(f"next_allowed_actions must be exactly {sorted(ALLOWED_NEXT_ACTIONS)}")

    forbidden = {item.lower() for item in _as_strings(state.get("forbidden_without_owner_approval"))}
    missing_forbidden = sorted(REQUIRED_FORBIDDEN - forbidden)
    if missing_forbidden:
        blockers.append(f"forbidden_without_owner_approval missing high-risk actions: {missing_forbidden}")

    work_package_policy = state.get("work_package_policy") if isinstance(state.get("work_package_policy"), dict) else {}
    if work_package_policy.get("selection_unit") != "bounded_low_risk_work_package":
        blockers.append("work_package_policy.selection_unit must be bounded_low_risk_work_package")
    if work_package_policy.get("target_duration_minutes_min") != 10:
        blockers.append("work_package_policy.target_duration_minutes_min must be 10")
    if work_package_policy.get("target_duration_minutes_max") != 13:
        blockers.append("work_package_policy.target_duration_minutes_max must be 13")
    for field in sorted(REQUIRED_WORK_PACKAGE_POLICY_TRUE):
        if work_package_policy.get(field) is not True:
            blockers.append(f"work_package_policy.{field} must be true")
    if work_package_policy.get("admin_merge_for_owner_decision_package_allowed") is not False:
        blockers.append("work_package_policy.admin_merge_for_owner_decision_package_allowed must be false")

    stop_conditions = _as_list(stop.get("high_risk_stop_conditions"))
    stop_ids = {str(item.get("id")) for item in stop_conditions if isinstance(item, dict)}
    missing_stop_ids = sorted(STOP_IDS - stop_ids)
    if missing_stop_ids:
        blockers.append(f"autonomous_stop_conditions missing stop ids: {missing_stop_ids}")

    stop_terms: set[str] = set()
    for item in stop_conditions:
        if isinstance(item, dict):
            stop_terms.update(str(term).lower() for term in _as_list(item.get("terms")))
    for action in next_allowed:
        normalized = action.replace("_", " ").lower()
        if any(term and term in normalized for term in stop_terms):
            blockers.append(f"next_allowed_action contains stop condition term: {action}")

    candidate = str(state.get("active_candidate", ""))
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    backlog_text = BACKLOG.read_text(encoding="utf-8")
    if candidate not in manifest_text:
        blockers.append("active_candidate not found in production_route_ownership_manifest.yaml")
    if candidate not in backlog_text:
        blockers.append("active_candidate not found in legacy_replacement_backlog.yaml")

    readiness = state.get("action_templates_readiness") if isinstance(state.get("action_templates_readiness"), dict) else {}
    for field in ("production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready"):
        if readiness.get(field) is not False:
            blockers.append(f"action_templates_readiness must not declare {field}")
    if readiness.get("paused") is not True:
        blockers.append("action_templates_readiness.paused must be true after owner decision package #644")
    if readiness.get("paused_by_pr") != "#644":
        blockers.append("action_templates_readiness.paused_by_pr must be #644")
    if readiness.get("owner_decision_required") is not True:
        blockers.append("action_templates_readiness.owner_decision_required must be true")

    paused_candidates = state.get("paused_candidates") if isinstance(state.get("paused_candidates"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/action-templates*"
        and item.get("paused_by_pr") == "#644"
        and item.get("owner_approval_required") is True
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must include action-templates awaiting owner decision from #644")

    task_groups_readiness = state.get("task_groups_readiness") if isinstance(state.get("task_groups_readiness"), dict) else {}
    if task_groups_readiness.get("native_contract_planning_started") is not True:
        blockers.append("task_groups_readiness.native_contract_planning_started must be true")
    if task_groups_readiness.get("native_contract_planning_completed") is not True:
        blockers.append("task_groups_readiness.native_contract_planning_completed must be true")
    for field in (
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if task_groups_readiness.get(field) is not False:
            blockers.append(f"task_groups_readiness.{field} must be false")

    changed = _changed_files()
    runtime_changed = [
        path
        for path in sorted(changed)
        if path.startswith("aicrm_next/")
        or path.startswith("wecom_ability_service/")
        or path.startswith("migrations/")
        or path.startswith("deploy/")
        or path.startswith("systemd/")
        or path.startswith("nginx/")
        or path in {"app.py", "legacy_flask_app.py"}
    ]
    if runtime_changed:
        blockers.append(f"autonomous loop PR must not touch runtime/protected files: {runtime_changed}")

    details["next_allowed_actions"] = sorted(next_allowed)
    details["forbidden_without_owner_approval"] = sorted(forbidden)
    details["work_package_policy"] = work_package_policy
    details["changed_files"] = sorted(changed)
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "warnings": warnings, "details": details}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Autonomous Development Loop Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
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
