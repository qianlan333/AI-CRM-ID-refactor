#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4ac_action_templates_companion_schema_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4ac_action_templates_companion_schema_plan.yaml"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    ROOT / "docs/development/phase_4ab_action_templates_schema_confirmation.md",
    ROOT / "docs/development/phase_4aa_action_templates_implementation_plan.md",
]
AUTH_FALSE_FIELDS = {
    "runtime_change_authorized",
    "migration_authorized",
    "production_repository_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "delete_ready",
}
IDEMPOTENCY_FIELDS = {
    "route_family",
    "operation",
    "operator",
    "idempotency_key",
    "request_hash",
    "response_snapshot",
    "resource_type",
    "resource_id",
    "status",
    "created_at",
    "updated_at",
}
IDEMPOTENCY_UNIQUE_FIELDS = {
    "route_family",
    "operation",
    "operator",
    "idempotency_key",
}
AUDIT_FIELDS = {
    "route_family",
    "operation",
    "operator",
    "resource_type",
    "resource_id",
    "before_snapshot",
    "after_snapshot",
    "request_payload",
    "validation_result",
    "rollback_payload",
    "side_effect_safety",
    "created_at",
}
SCOPE_CONSTRAINTS = {
    "generate_route_excluded",
    "from_workflow_route_deferred",
    "deepseek_llm_adapter_excluded",
    "workflow_execution_excluded",
    "outbound_send_excluded",
    "timer_excluded",
    "openclaw_mcp_excluded",
    "wecom_external_call_excluded",
}
MIGRATION_READINESS = {
    "additive_only_required": True,
    "main_table_mutation_forbidden": True,
    "backfill_forbidden": True,
    "destructive_sql_forbidden": True,
    "deployment_requires_owner_approval": True,
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4ac_action_templates_companion_schema_plan.md",
    "docs/development/phase_4ac_action_templates_companion_schema_plan.yaml",
    "tools/check_phase4ac_action_templates_companion_schema_plan.py",
    "tests/test_phase4ac_action_templates_companion_schema_plan.py",
    "tools/check_phase4ab_action_templates_schema_confirmation.py",
    "tools/check_phase4aa_action_templates_implementation_plan.py",
    "tools/check_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
    "docs/development/phase_4ad_action_templates_companion_migration.md",
    "docs/development/phase_4ad_action_templates_companion_migration.yaml",
    "tools/check_phase4ad_action_templates_companion_migration.py",
    "tests/test_phase4ad_action_templates_companion_migration.py",
    "wecom_ability_service/schema_postgres.sql",
    "wecom_ability_service/db/migrations/postgres_migrations.py",
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
FORBIDDEN_DOC_PHRASES = [
    "migration created",
    "runtime implemented",
    "production repository enabled",
    "production write authorized",
    "route switch authorized",
    "fallback removal authorized",
    "production approved",
    "canary approved",
    "delete_ready true",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip("\"'") for part in inner.split(",")]
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
                value: Any = _parse_scalar(item_text)
                if index < len(lines) and lines[index][0] > indent:
                    nested, index = _parse_yaml_block(lines, index, indent + 2)
                    if isinstance(nested, dict):
                        value = {"value": value, **nested}
                result.append(value)
                continue
            key, raw_value = item_text.split(":", 1)
            item: dict[str, Any] = {}
            raw_value = raw_value.strip()
            if raw_value:
                item[key.strip()] = _parse_scalar(raw_value)
            else:
                value, index = _parse_yaml_block(lines, index, indent + 2)
                item[key.strip()] = value
            if index < len(lines) and lines[index][0] > indent:
                nested, index = _parse_yaml_block(lines, index, indent + 2)
                if isinstance(nested, dict):
                    item.update(nested)
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


def _field_names(values: Any) -> set[str]:
    return {str(item.get("name")) for item in _as_list(values) if isinstance(item, dict) and item.get("name")}


def _constraint_fields(values: Any) -> set[str]:
    fields: set[str] = set()
    for item in _as_list(values):
        if isinstance(item, dict):
            fields.update(str(field) for field in _as_list(item.get("fields")))
    return fields


def _run(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def _changed_files_from_git() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for command in (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        code, output = _run(command)
        if code == 0:
            changed.update(line.strip() for line in output.splitlines() if line.strip())
        else:
            warnings.append(f"{' '.join(command)} unavailable: {output}")
    return changed, warnings


def check_required_docs() -> dict[str, Any]:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_DOCS if not path.exists()]
    return {"ok": not missing, "blockers": [f"missing required file: {path}" for path in missing], "warnings": []}


def check_authorizations(data: dict[str, Any] | None = None) -> dict[str, Any]:
    auth = (data or load_yaml()).get("authorizations") or {}
    blockers = [
        f"authorizations.{field} must be false"
        for field in sorted(AUTH_FALSE_FIELDS)
        if auth.get(field) is not False
    ]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_route_owner_and_table(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if data.get("route_family") != "/api/admin/automation-conversion/action-templates*":
        blockers.append("route_family must be /api/admin/automation-conversion/action-templates*")
    if data.get("capability_owner") != "aicrm_next.automation_engine":
        blockers.append("capability_owner must be aicrm_next.automation_engine")
    if data.get("integration_fallback_boundary") != "aicrm_next.integration_gateway":
        blockers.append("integration_fallback_boundary must be aicrm_next.integration_gateway")
    if data.get("main_table") != "automation_operation_templates":
        blockers.append("main_table must be automation_operation_templates")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_schema_need(data: dict[str, Any] | None = None) -> dict[str, Any]:
    need = (data or load_yaml()).get("schema_need") or {}
    blockers: list[str] = []
    for field in ("idempotency_storage_required", "audit_storage_required", "before_after_snapshot_required"):
        if need.get(field) is not True:
            blockers.append(f"schema_need.{field} must be true")
    if not _as_list(need.get("reason")):
        blockers.append("schema_need.reason must be non-empty")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_idempotency_plan(data: dict[str, Any] | None = None) -> dict[str, Any]:
    plan = (data or load_yaml()).get("idempotency_schema_plan") or {}
    blockers: list[str] = []
    if plan.get("strategy") != "new_companion_table":
        blockers.append("idempotency_schema_plan.strategy must be new_companion_table")
    if not plan.get("proposed_table"):
        blockers.append("idempotency_schema_plan.proposed_table must be non-empty")
    missing = sorted(IDEMPOTENCY_FIELDS - _field_names(plan.get("required_fields")))
    if missing:
        blockers.append(f"idempotency_schema_plan.required_fields missing {missing}")
    missing_unique = sorted(IDEMPOTENCY_UNIQUE_FIELDS - _constraint_fields(plan.get("unique_constraints")))
    if missing_unique:
        blockers.append(f"idempotency_schema_plan.unique_constraints missing {missing_unique}")
    for field in ("conflict_behavior", "replay_behavior", "retention_policy"):
        if not plan.get(field):
            blockers.append(f"idempotency_schema_plan.{field} must be non-empty")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_audit_plan(data: dict[str, Any] | None = None) -> dict[str, Any]:
    plan = (data or load_yaml()).get("audit_schema_plan") or {}
    blockers: list[str] = []
    if plan.get("strategy") != "new_companion_table":
        blockers.append("audit_schema_plan.strategy must be new_companion_table")
    if not plan.get("proposed_table"):
        blockers.append("audit_schema_plan.proposed_table must be non-empty")
    missing = sorted(AUDIT_FIELDS - _field_names(plan.get("required_fields")))
    if missing:
        blockers.append(f"audit_schema_plan.required_fields missing {missing}")
    for field in ("snapshot_policy", "rollback_payload_policy", "retention_policy"):
        if not plan.get(field):
            blockers.append(f"audit_schema_plan.{field} must be non-empty")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_scope_constraints(data: dict[str, Any] | None = None) -> dict[str, Any]:
    constraints = (data or load_yaml()).get("scope_constraints") or {}
    blockers = [
        f"scope_constraints.{field} must be true"
        for field in sorted(SCOPE_CONSTRAINTS)
        if constraints.get(field) is not True
    ]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_migration_readiness(data: dict[str, Any] | None = None) -> dict[str, Any]:
    readiness = (data or load_yaml()).get("migration_readiness") or {}
    blockers: list[str] = []
    if readiness.get("migration_artifact_authorized_now") is not False:
        blockers.append("migration_readiness.migration_artifact_authorized_now must be false")
    for field, expected in MIGRATION_READINESS.items():
        if readiness.get(field) is not expected:
            blockers.append(f"migration_readiness.{field} must be {str(expected).lower()}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase_4ad_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = (data or load_yaml()).get("phase_4ad_recommendation") or {}
    blockers: list[str] = []
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4ad_recommendation.recommended_next_step missing")
    for field in (
        "migration_allowed_without_owner_approval",
        "runtime_implementation_allowed",
        "production_route_switch_allowed",
        "fallback_removal_allowed",
        "production_write_canary_allowed",
    ):
        if rec.get(field) is not False:
            blockers.append(f"phase_4ad_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4AC scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_doc_claims() -> dict[str, Any]:
    text = _read(DOC).lower()
    blockers: list[str] = []
    for phrase in FORBIDDEN_DOC_PHRASES:
        if phrase in text:
            blockers.append(f"doc appears to claim forbidden state: {phrase}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def build_report() -> dict[str, Any]:
    data = load_yaml()
    checks = {
        "required_docs": check_required_docs(),
        "authorizations": check_authorizations(data),
        "route_owner_and_table": check_route_owner_and_table(data),
        "schema_need": check_schema_need(data),
        "idempotency_plan": check_idempotency_plan(data),
        "audit_plan": check_audit_plan(data),
        "scope_constraints": check_scope_constraints(data),
        "migration_readiness": check_migration_readiness(data),
        "phase_4ad_recommendation": check_phase_4ad_recommendation(data),
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
        "# Phase 4AC Action Templates Companion Schema Plan Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4AC action-templates companion schema plan.")
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
