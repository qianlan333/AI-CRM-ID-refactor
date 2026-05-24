#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4al_action_templates_staging_execution_ready_gate.md"
YAML_DOC = ROOT / "docs/development/phase_4al_action_templates_staging_execution_ready_gate.yaml"
PREFLIGHT = ROOT / "tools/run_phase4al_action_templates_staging_execution_preflight.py"
REQUIRED_DOCS = [DOC, YAML_DOC, PREFLIGHT]
AUTH_FALSE_FIELDS = {
    "staging_smoke_execution_authorized",
    "production_repository_route_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "production_write_authorized",
    "delete_ready",
}
BLOCKER_HISTORY = {
    "phase_4aj_package_exists": True,
    "phase_4ak_evidence_gate_exists": True,
    "phase_4ak_default_blocked_missing_staging_db": True,
    "staging_smoke_executed": False,
}
CLOSURE_FIELDS = {
    "automation_engine_owner_approval",
    "integration_gateway_owner_approval",
    "staging_db_config_owner_approval",
    "rollback_owner_assigned",
    "smoke_operator_assigned",
    "staging_db_env_confirmed",
    "staging_db_url_safety_confirmed",
    "repo_backend_confirmed",
    "read_only_preflight_confirmed",
    "write_smoke_approval_confirmed",
    "safe_namespace_confirmed",
    "evidence_path_confirmed",
    "cleanup_strategy_confirmed",
    "side_effect_safety_confirmed",
}
PHASE_4AM_CONSTRAINTS = {
    "staging_only",
    "production_data_forbidden",
    "production_route_switch_forbidden",
    "fallback_removal_forbidden",
    "production_compat_change_forbidden",
    "external_calls_forbidden",
    "generate_from_workflow_forbidden",
    "update_delete_forbidden",
}
ALLOWED_CHANGED_FILES = {
    "tools/run_phase4al_action_templates_staging_execution_preflight.py",
    "docs/development/phase_4al_action_templates_staging_execution_ready_gate.md",
    "docs/development/phase_4al_action_templates_staging_execution_ready_gate.yaml",
    "tools/check_phase4al_action_templates_staging_execution_ready_gate.py",
    "tests/test_phase4al_action_templates_staging_execution_ready_gate.py",
    "tools/check_phase4ak_action_templates_staging_smoke_evidence.py",
    "tools/check_phase4aj_action_templates_staging_smoke_package.py",
    "tools/check_phase4ai_action_templates_test_db_parity.py",
}
PROTECTED_EXACT = {
    "aicrm_next/main.py",
    "aicrm_next/production_compat/api.py",
    "app.py",
    "legacy_flask_app.py",
}
PROTECTED_PREFIXES = (
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "systemd/",
    "nginx/",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
            result.append(item)
        return result, index
    result: dict[str, Any] = {}
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent != indent or text.startswith("- "):
            break
        key, raw_value = text.split(":", 1)
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            result[key.strip()] = _parse_scalar(raw_value)
        else:
            value, index = _parse_yaml_block(lines, index, indent + 2)
            result[key.strip()] = value
    return result, index


def _load_yaml_without_dependency(text: str) -> dict[str, Any]:
    data, _ = _parse_yaml_block(_yaml_lines(text), 0, 0)
    return data if isinstance(data, dict) else {}


def load_yaml(path: Path = YAML_DOC) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        return _load_yaml_without_dependency(text)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return False, proc.stdout, proc.stderr
    return True, proc.stdout, proc.stderr


def _changed_files_from_git() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only", "--cached"]):
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


def check_required_docs() -> dict[str, Any]:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_DOCS if not path.exists()]
    return {"ok": not missing, "blockers": [f"missing required artifact: {path}" for path in missing], "warnings": []}


def check_yaml_contract(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if data.get("status") != "phase_4al_action_templates_staging_execution_ready_gate_no_execution":
        blockers.append("status must be phase_4al_action_templates_staging_execution_ready_gate_no_execution")
    for field in sorted(AUTH_FALSE_FIELDS):
        if (data.get("authorizations") or {}).get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")
    history = data.get("blocker_history") or {}
    for field, expected in BLOCKER_HISTORY.items():
        if history.get(field) is not expected:
            blockers.append(f"blocker_history.{field} must be {expected}")
    closure = data.get("closure_form") or {}
    for field in sorted(CLOSURE_FIELDS):
        if closure.get(field) != "pending":
            blockers.append(f"closure_form.{field} must default pending")
    tool = data.get("preflight_tool") or {}
    if tool.get("path") != "tools/run_phase4al_action_templates_staging_execution_preflight.py":
        blockers.append("preflight_tool.path must point to Phase 4AL preflight tool")
    for field in ("db_connection_allowed", "lower_runner_call_allowed", "staging_smoke_execution_allowed"):
        if tool.get(field) is not False:
            blockers.append(f"preflight_tool.{field} must be false")
    for field in ("supports_closure_status_file", "supports_env_check", "supports_cli_arg_check"):
        if tool.get(field) is not True:
            blockers.append(f"preflight_tool.{field} must be true")
    gate = data.get("execution_gate") or {}
    if gate.get("ready_for_phase_4am_staging_execution") is not False:
        blockers.append("execution_gate.ready_for_phase_4am_staging_execution must default false")
    for field in ("missing_items", "unblock_actions", "next_owner_actions", "next_config_actions", "next_evidence_actions"):
        if not _as_list(gate.get(field)):
            blockers.append(f"execution_gate.{field} must be non-empty")
    constraints = data.get("phase_4am_constraints") or {}
    for field in sorted(PHASE_4AM_CONSTRAINTS):
        if constraints.get(field) is not True:
            blockers.append(f"phase_4am_constraints.{field} must be true")
    recommendation = data.get("phase_4am_recommendation") or {}
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_4am_recommendation.recommended_next_step missing")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if recommendation.get(field) is not False:
            blockers.append(f"phase_4am_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_preflight_static() -> dict[str, Any]:
    blockers: list[str] = []
    text = _read(PREFLIGHT)
    for token in (
        "--closure-status-file",
        "--read-only",
        "--confirm-no-production",
        "--confirm-no-external-calls",
        "--output-json",
        "--output-md",
        "AICRM_ACTION_TEMPLATES_REPO_BACKEND",
        "AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL",
        "AICRM_PHASE4AK_STAGING_SMOKE_APPROVED",
    ):
        if token not in text:
            blockers.append(f"preflight tool missing token: {token}")
    for forbidden in (
        "create_engine",
        "run_phase4aj_action_templates_staging_smoke",
        "run_phase4ak_action_templates_staging_smoke_evidence",
        "wecom_ability_service",
        "DeepSeek",
        "deepseek",
        "llm_adapter",
        "action-templates/generate",
        "action-templates/from-workflow",
        ".delete(",
        ".put(",
        "update_action_template",
        "delete_action_template",
    ):
        if forbidden in text:
            blockers.append(f"preflight tool contains forbidden token: {forbidden}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4AL scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    for blocked in ("aicrm_next/main.py", "aicrm_next/production_compat/api.py"):
        if blocked in changed:
            blockers.append(f"{blocked} must remain unchanged")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_doc_claims() -> dict[str, Any]:
    text = _read(DOC).lower()
    blockers: list[str] = []
    for pattern in (
        r"staging smoke executed",
        r"production parity",
        r"production repository enabled as route owner",
        r"production write authorized",
        r"route switch authorized",
        r"fallback removal authorized",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ):
        if re.search(pattern, text):
            blockers.append(f"doc appears to claim forbidden state: {pattern}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def build_report() -> dict[str, Any]:
    data = load_yaml()
    checks = {
        "required_docs": check_required_docs(),
        "yaml_contract": check_yaml_contract(data),
        "preflight_static": check_preflight_static(),
        "change_scope": check_change_scope(),
        "doc_claims": check_doc_claims(),
    }
    blockers: list[str] = []
    warnings: list[str] = []
    for name, check in checks.items():
        for blocker in check.get("blockers", []):
            blockers.append(f"{name}: {blocker}")
        for warning in check.get("warnings", []):
            warnings.append(f"{name}: {warning}")
    return {
        "overall": "PASS" if not blockers else "FAIL",
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4AL Action Templates Staging Execution Ready Gate Check",
        "",
        f"- overall: {report['overall']}",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers") or []
    lines.extend(f"- {blocker}" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Warnings"])
    warnings = report.get("warnings") or []
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("- none")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Phase 4AL action templates staging execution ready gate.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"overall: {report['overall']}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
