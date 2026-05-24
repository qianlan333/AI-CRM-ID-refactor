#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN_MD = ROOT / "docs/development/phase_4ag_action_templates_repository_adapter_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4ag_action_templates_repository_adapter_plan.yaml"
REQUIRED_DOCS = [PLAN_MD, PLAN_YAML]
AUTH_FALSE_FIELDS = {
    "runtime_implementation_authorized",
    "production_repository_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "production_write_authorized",
    "delete_ready",
}
REQUIRED_METHODS = {
    "list_action_templates",
    "create_action_template",
    "list_action_template_audit_events",
}
REQUIRED_EXCLUDED_METHODS = {
    "generate_action_template",
    "create_action_template_from_workflow",
    "update_action_template",
    "delete_action_template",
    "execute_action_template",
    "send_action_template",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4ag_action_templates_repository_adapter_plan.md",
    "docs/development/phase_4ag_action_templates_repository_adapter_plan.yaml",
    "tools/check_phase4ag_action_templates_repository_adapter_plan.py",
    "tests/test_phase4ag_action_templates_repository_adapter_plan.py",
    "tools/check_phase4af_action_templates_local_parity_harness.py",
    "tools/check_phase4ae_action_templates_native_fixture_contract.py",
    "tools/check_phase4ad_action_templates_companion_migration.py",
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
            while index < len(lines):
                child_indent, child_text = lines[index]
                if child_indent <= indent:
                    break
                if child_indent == indent + 2 and not child_text.startswith("- ") and ":" in child_text:
                    child_key, child_raw_value = child_text.split(":", 1)
                    child_raw_value = child_raw_value.strip()
                    index += 1
                    if child_raw_value:
                        item[child_key.strip()] = _parse_scalar(child_raw_value)
                    else:
                        value, index = _parse_yaml_block(lines, index, child_indent + 2)
                        item[child_key.strip()] = value
                else:
                    break
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


def load_yaml(path: Path = PLAN_YAML) -> dict[str, Any]:
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
    return {"ok": not missing, "blockers": [f"missing required doc: {path}" for path in missing], "warnings": []}


def check_yaml_contract(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if data.get("status") != "phase_4ag_action_templates_repository_adapter_planning_no_runtime_change":
        blockers.append("status must be phase_4ag_action_templates_repository_adapter_planning_no_runtime_change")
    for field in sorted(AUTH_FALSE_FIELDS):
        if (data.get("authorizations") or {}).get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    planned_repository = data.get("planned_repository") or {}
    if not planned_repository.get("class_name"):
        blockers.append("planned_repository.class_name must be non-empty")
    expected_repo = {
        "backend_flag": "AICRM_ACTION_TEMPLATES_REPO_BACKEND",
        "database_url_flag": "AICRM_ACTION_TEMPLATES_DATABASE_URL",
        "default_backend": "fixture",
    }
    for field, expected in expected_repo.items():
        if planned_repository.get(field) != expected:
            blockers.append(f"planned_repository.{field} must be {expected}")
    if planned_repository.get("database_url_fallback_allowed") is not False:
        blockers.append("planned_repository.database_url_fallback_allowed must be false")
    if planned_repository.get("production_route_owner_unchanged") is not True:
        blockers.append("planned_repository.production_route_owner_unchanged must be true")

    tables = data.get("tables") or {}
    expected_tables = {
        "main": "automation_operation_templates",
        "idempotency": "automation_operation_template_idempotency",
        "audit": "automation_operation_template_audit_log",
    }
    for field, expected in expected_tables.items():
        if tables.get(field) != expected:
            blockers.append(f"tables.{field} must be {expected}")

    methods = {str(item.get("name") or ""): item for item in _as_list(data.get("planned_methods")) if isinstance(item, dict)}
    missing_methods = sorted(REQUIRED_METHODS - set(methods))
    if missing_methods:
        blockers.append(f"planned_methods missing {missing_methods}")
    create = methods.get("create_action_template") or {}
    for field in ("transaction_required", "idempotency_required", "audit_required", "rollback_required"):
        if create.get(field) is not True:
            blockers.append(f"planned_methods.create_action_template.{field} must be true")
    for method_name, method in methods.items():
        if method.get("external_side_effect_allowed") is not False:
            blockers.append(f"planned_methods.{method_name}.external_side_effect_allowed must be false")

    excluded = {str(item) for item in _as_list(data.get("excluded_methods"))}
    missing_excluded = sorted(REQUIRED_EXCLUDED_METHODS - excluded)
    if missing_excluded:
        blockers.append(f"excluded_methods missing {missing_excluded}")

    for section_name in ("idempotency_strategy", "enablement_strategy", "parity_smoke_readiness"):
        section = data.get(section_name) or {}
        for field, value in section.items():
            if value is not True:
                blockers.append(f"{section_name}.{field} must be true")
    audit = data.get("audit_strategy") or {}
    for field in ("audit_event_required", "after_snapshot_required", "rollback_payload_required", "side_effect_safety_required"):
        if audit.get(field) is not True:
            blockers.append(f"audit_strategy.{field} must be true")
    if audit.get("before_snapshot_for_create") != "empty_object":
        blockers.append("audit_strategy.before_snapshot_for_create must be empty_object")

    recommendation = data.get("phase_4ah_recommendation") or {}
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_4ah_recommendation.recommended_next_step missing")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if recommendation.get(field) is not False:
            blockers.append(f"phase_4ah_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4AG scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_doc_claims() -> dict[str, Any]:
    text = _read(PLAN_MD).lower()
    blockers: list[str] = []
    for pattern in (
        r"repository implemented",
        r"production repository enabled",
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
        "# Phase 4AG Action Templates Repository Adapter Plan Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4AG action templates repository adapter planning.")
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
