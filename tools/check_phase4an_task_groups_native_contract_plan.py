#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4an_task_groups_native_contract_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4an_task_groups_native_contract_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

ROUTE = "/api/admin/automation-conversion/task-groups*"
REQUIRED_SCOPE = {
    "route_surface_confirmation",
    "metadata_only_subset_decision",
    "request_response_field_mapping",
    "validation_boundary_plan",
    "idempotency_plan",
    "audit_plan",
    "rollback_payload_plan",
    "fixture_local_contract_plan",
    "checker_and_test_plan",
}
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
EXCLUDED_TRUE_FIELDS = {
    "payment",
    "oauth",
    "wecom_external_call",
    "openclaw_mcp_real_call",
    "timer_execution",
    "automation_execution",
    "outbound_send",
    "media_upload",
    "production_write",
    "production_route_switch",
    "fallback_removal",
    "production_compat_change",
}
REQUIRED_GUARDRAILS = {
    "keep_legacy_fallback",
    "no_production_owner_switch",
    "no_production_write",
    "no_external_calls",
    "fixture_local_evidence_not_production_success",
    "idempotency_audit_rollback_before_native_write",
    "staging_and_owner_approval_before_production_use",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.md",
    "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.yaml",
    "docs/development/phase_4an_task_groups_native_contract_plan.md",
    "docs/development/phase_4an_task_groups_native_contract_plan.yaml",
    "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.md",
    "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.yaml",
    "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.md",
    "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
    "tools/check_phase4an_task_groups_native_contract_plan.py",
    "tools/check_phase4ao_task_groups_schema_route_surface_confirmation.py",
    "tools/check_phase4ap_task_groups_fixture_native_contract_plan.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
    "tests/test_phase4an_task_groups_native_contract_plan.py",
    "tests/test_phase4ao_task_groups_schema_route_surface_confirmation.py",
    "tests/test_phase4ap_task_groups_fixture_native_contract_plan.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
PROTECTED_PREFIXES = (
    "aicrm_next/",
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "systemd/",
    "nginx/",
)
PROTECTED_EXACT = {"app.py", "legacy_flask_app.py"}
FORBIDDEN_DOC_CLAIMS = {
    "production_ready",
    "delete_ready true",
    "delete_ready: true",
    "canary_approved",
    "canary approved",
    "route_switch_ready=true",
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
    for args in (
        ["diff", "--name-only", "origin/main...HEAD"],
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
    ):
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

    if data.get("status") != "phase_4an_task_groups_native_contract_planning_no_runtime_change":
        blockers.append("status must be phase_4an_task_groups_native_contract_planning_no_runtime_change")
    if data.get("route_family") != ROUTE:
        blockers.append("route_family must be task-groups wildcard")
    if ROUTE not in manifest_text or ROUTE not in backlog_text:
        blockers.append("task-groups route must exist in manifest and backlog")
    if data.get("current_runtime_owner") != "production_compat":
        blockers.append("current_runtime_owner must remain production_compat")
    if data.get("production_behavior") != "legacy_forward":
        blockers.append("production_behavior must remain legacy_forward")
    if data.get("legacy_fallback_retained") is not True:
        blockers.append("legacy_fallback_retained must be true")

    previous = data.get("previous_candidate") if isinstance(data.get("previous_candidate"), dict) else {}
    if previous.get("paused_by_pr") != "#644":
        blockers.append("previous action-templates candidate must be paused by #644")
    if previous.get("owner_approval_required") is not True:
        blockers.append("previous action-templates candidate must require owner approval")

    selected = data.get("selected_candidate") if isinstance(data.get("selected_candidate"), dict) else {}
    if selected.get("route_family") != ROUTE:
        blockers.append("selected_candidate.route_family mismatch")
    if selected.get("replacement_phase") != "phase_4_internal_write":
        blockers.append("selected_candidate.replacement_phase must be phase_4_internal_write")
    if selected.get("replacement_category") != "internal_write":
        blockers.append("selected_candidate.replacement_category must be internal_write")

    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    if not REQUIRED_SCOPE <= set(data.get("planned_contract_scope") or []):
        blockers.append("planned_contract_scope incomplete")
    excluded = data.get("excluded_scope") if isinstance(data.get("excluded_scope"), dict) else {}
    for field in sorted(EXCLUDED_TRUE_FIELDS):
        if excluded.get(field) is not True:
            blockers.append(f"excluded_scope.{field} must be true")
    if not REQUIRED_GUARDRAILS <= set(data.get("required_guardrails") or []):
        blockers.append("required_guardrails incomplete")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state_update.get("phase_4an_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4AN completed step")
    paused = state.get("paused_candidates") if isinstance(state.get("paused_candidates"), list) else []
    if not any(isinstance(item, dict) and item.get("route_family") == "/api/admin/automation-conversion/action-templates*" and item.get("paused_by_pr") == "#644" for item in paused):
        blockers.append("phase_execution_state.paused_candidates must include action-templates paused by #644")

    readiness = state.get("task_groups_readiness") if isinstance(state.get("task_groups_readiness"), dict) else {}
    for field in ("production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if readiness.get(field) is not False:
            blockers.append(f"task_groups_readiness.{field} must be false")

    rec = data.get("phase_4ao_recommendation") if isinstance(data.get("phase_4ao_recommendation"), dict) else {}
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4ao_recommendation.recommended_next_step required")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4ao_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4AN package: {unexpected}")
    protected = sorted(
        path for path in changed if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)
    )
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")

    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "details": {"changed_files": sorted(changed)},
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4AN Task Groups Native Contract Plan Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
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
    print(f"overall: {report['overall']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
