#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN_MD = ROOT / "docs/development/phase_4ad_action_templates_companion_migration.md"
PLAN_YAML = ROOT / "docs/development/phase_4ad_action_templates_companion_migration.yaml"
SCHEMA_SQL = ROOT / "wecom_ability_service/schema_postgres.sql"
POSTGRES_MIGRATIONS = ROOT / "wecom_ability_service/db/migrations/postgres_migrations.py"
REQUIRED_DOCS = [
    PLAN_MD,
    PLAN_YAML,
    ROOT / "docs/development/phase_4ac_action_templates_companion_schema_plan.md",
    ROOT / "docs/development/phase_4ab_action_templates_schema_confirmation.md",
]
AUTH_FALSE_FIELDS = {
    "runtime_change_authorized",
    "production_repository_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "delete_ready",
}
REQUIRED_SCOPE_TRUE = {
    "additive_only",
    "no_existing_table_mutation",
    "no_backfill",
    "no_runtime_usage",
}
IDEMPOTENCY_TABLE = "automation_operation_template_idempotency"
AUDIT_TABLE = "automation_operation_template_audit_log"
REQUIRED_IDEMPOTENCY_FIELDS = {
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
REQUIRED_IDEMPOTENCY_UNIQUE_FIELDS = {
    "route_family",
    "operation",
    "operator",
    "idempotency_key",
}
REQUIRED_AUDIT_FIELDS = {
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
MIGRATION_ARTIFACTS = {
    "wecom_ability_service/schema_postgres.sql",
    "wecom_ability_service/db/migrations/postgres_migrations.py",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4ad_action_templates_companion_migration.md",
    "docs/development/phase_4ad_action_templates_companion_migration.yaml",
    "tools/check_phase4ad_action_templates_companion_migration.py",
    "tests/test_phase4ad_action_templates_companion_migration.py",
    "tools/check_phase4ac_action_templates_companion_schema_plan.py",
    "tools/check_phase4ab_action_templates_schema_confirmation.py",
    "tools/check_phase4aa_action_templates_implementation_plan.py",
    "aicrm_next/automation_engine/api.py",
    "aicrm_next/automation_engine/application.py",
    "aicrm_next/automation_engine/dto.py",
    "aicrm_next/automation_engine/action_templates.py",
    "aicrm_next/automation_engine/action_template_repository.py",
    "docs/development/phase_4ae_action_templates_native_fixture_contract.md",
    "docs/development/phase_4ae_action_templates_native_fixture_contract.yaml",
    "tools/check_phase4ae_action_templates_native_fixture_contract.py",
    "tests/test_phase4ae_action_templates_native_fixture_contract.py",
    "tools/run_phase4af_action_templates_local_parity.py",
    "docs/development/phase_4af_action_templates_local_parity_harness.md",
    "docs/development/phase_4af_action_templates_local_parity_harness.yaml",
    "tools/check_phase4af_action_templates_local_parity_harness.py",
    "tests/test_phase4af_action_templates_local_parity_harness.py",
    "docs/development/phase_4ag_action_templates_repository_adapter_plan.md",
    "docs/development/phase_4ag_action_templates_repository_adapter_plan.yaml",
    "tools/check_phase4ag_action_templates_repository_adapter_plan.py",
    "tests/test_phase4ag_action_templates_repository_adapter_plan.py",
    *MIGRATION_ARTIFACTS,
}
PROTECTED_PREFIXES = (
    "aicrm_next/",
    "wecom_ability_service/http/",
    "wecom_ability_service/domains/",
    "deploy",
    "systemd",
    "nginx",
)
PROTECTED_EXACT = {
    "aicrm_next/main.py",
    "aicrm_next/production_compat/api.py",
    "app.py",
    "legacy_flask_app.py",
}
DESTRUCTIVE_PATTERNS = [
    r"\bDROP\s+TABLE\b",
    r"\bDROP\s+COLUMN\b",
    r"\bALTER\s+TABLE\b.*\bDROP\b",
    r"\bRENAME\s+TABLE\b",
    r"\bRENAME\s+COLUMN\b",
    r"\bDELETE\s+FROM\b",
    r"\bUPDATE\s+automation_operation_templates\b",
    r"\bUPDATE\s+automation_profile_segment_template\b",
    r"\bUPDATE\s+automation_profile_segment_category\b",
    r"\bUPDATE\s+automation_profile_segment_option_mapping\b",
]


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
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
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


def _git_diff_text() -> tuple[str, list[str]]:
    warnings: list[str] = []
    chunks: list[str] = []
    for args in (["diff", "origin/main...HEAD"], ["diff", "--cached"]):
        ok, stdout, stderr = _run_git(args)
        if ok:
            chunks.append(stdout)
        else:
            warnings.append(f"git {' '.join(args)} unavailable: {(stderr or stdout).strip()}")
    return "\n".join(chunks), warnings


def check_required_docs() -> dict[str, Any]:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_DOCS if not path.exists()]
    return {"ok": not missing, "blockers": [f"missing required doc: {path}" for path in missing], "warnings": []}


def check_authorizations(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    authorizations = data.get("authorizations") or {}
    blockers: list[str] = []
    if data.get("status") != "phase_4ad_action_templates_companion_schema_migration_artifact_no_runtime_change":
        blockers.append("status must be phase_4ad_action_templates_companion_schema_migration_artifact_no_runtime_change")
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_migration_scope(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    scope = data.get("migration_scope") or {}
    blockers = [f"migration_scope.{field} must be true" for field in sorted(REQUIRED_SCOPE_TRUE) if scope.get(field) is not True]
    if scope.get("deployment_authorized") is not False:
        blockers.append("migration_scope.deployment_authorized must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _table_by_name(data: dict[str, Any], table_name: str) -> dict[str, Any]:
    for table in _as_list(data.get("tables")):
        if isinstance(table, dict) and table.get("name") == table_name:
            return table
    return {}


def _field_names(table: dict[str, Any]) -> set[str]:
    return {str(item.get("name") or "") for item in _as_list(table.get("fields")) if isinstance(item, dict)}


def _constraint_field_sets(table: dict[str, Any]) -> list[set[str]]:
    return [
        {str(field) for field in _as_list(item.get("fields"))}
        for item in _as_list(table.get("unique_constraints"))
        if isinstance(item, dict)
    ]


def check_tables(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    idempotency = _table_by_name(data, IDEMPOTENCY_TABLE)
    audit = _table_by_name(data, AUDIT_TABLE)
    if not idempotency:
        blockers.append(f"missing table entry: {IDEMPOTENCY_TABLE}")
    if not audit:
        blockers.append(f"missing table entry: {AUDIT_TABLE}")
    if idempotency:
        missing_fields = sorted(REQUIRED_IDEMPOTENCY_FIELDS - _field_names(idempotency))
        if missing_fields:
            blockers.append(f"{IDEMPOTENCY_TABLE} missing fields {missing_fields}")
        if not any(REQUIRED_IDEMPOTENCY_UNIQUE_FIELDS <= field_set for field_set in _constraint_field_sets(idempotency)):
            blockers.append(f"{IDEMPOTENCY_TABLE} unique constraint must include {sorted(REQUIRED_IDEMPOTENCY_UNIQUE_FIELDS)}")
        if not _as_list(idempotency.get("indexes")):
            blockers.append(f"{IDEMPOTENCY_TABLE} indexes missing")
    if audit:
        missing_fields = sorted(REQUIRED_AUDIT_FIELDS - _field_names(audit))
        if missing_fields:
            blockers.append(f"{AUDIT_TABLE} missing fields {missing_fields}")
        if audit.get("unique_constraints") != []:
            blockers.append(f"{AUDIT_TABLE} unique_constraints must be []")
        if not _as_list(audit.get("indexes")):
            blockers.append(f"{AUDIT_TABLE} indexes missing")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_business_continuity(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    continuity = data.get("business_continuity") or {}
    recommendation = data.get("phase_4ae_recommendation") or {}
    blockers: list[str] = []
    for field in (
        "fallback_retained",
        "production_routes_unchanged",
        "production_compat_unchanged",
        "deploy_required_before_effective",
        "smoke_required_before_use",
    ):
        if continuity.get(field) is not True:
            blockers.append(f"business_continuity.{field} must be true")
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_4ae_recommendation.recommended_next_step missing")
    for field in (
        "runtime_implementation_allowed_without_owner_approval",
        "production_repository_allowed_without_owner_approval",
        "route_switch_allowed",
        "fallback_removal_allowed",
    ):
        if recommendation.get(field) is not False:
            blockers.append(f"phase_4ae_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_migration_artifacts() -> dict[str, Any]:
    blockers: list[str] = []
    text = "\n".join(_read(path) for path in (SCHEMA_SQL, POSTGRES_MIGRATIONS) if path.exists())
    for table_name in (IDEMPOTENCY_TABLE, AUDIT_TABLE):
        if table_name not in text:
            blockers.append(f"{table_name} missing from schema/migration artifacts")
    required_snippets = [
        "CREATE TABLE IF NOT EXISTS automation_operation_template_idempotency",
        "CREATE TABLE IF NOT EXISTS automation_operation_template_audit_log",
        "UNIQUE (route_family, operation, operator, idempotency_key)",
        "idx_action_template_idempotency_resource",
        "idx_action_template_idempotency_status",
        "idx_action_template_audit_resource",
        "idx_action_template_audit_operator",
        "idx_action_template_audit_operation",
        "_ensure_postgres_action_template_companion_tables(db)",
    ]
    for snippet in required_snippets:
        if snippet not in text:
            blockers.append(f"migration artifact missing snippet: {snippet}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected_runtime_file(path: str) -> bool:
    if path in PROTECTED_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected_runtime_file(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4AD migration readiness scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def _added_diff_lines(diff_text: str) -> str:
    lines: list[str] = []
    current_file = ""
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            parts = raw.split()
            current_file = parts[-1][2:] if len(parts) >= 4 and parts[-1].startswith("b/") else ""
            continue
        if current_file not in MIGRATION_ARTIFACTS:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            lines.append(raw[1:])
    return "\n".join(lines)


def check_no_destructive_sql() -> dict[str, Any]:
    diff_text, warnings = _git_diff_text()
    added = _added_diff_lines(diff_text)
    blockers: list[str] = []
    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, added, flags=re.IGNORECASE | re.DOTALL):
            blockers.append(f"destructive SQL added in migration artifact: {pattern}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings}


def check_doc_claims() -> dict[str, Any]:
    text = _read(PLAN_MD).lower()
    blockers: list[str] = []
    forbidden_patterns = [
        r"runtime implemented",
        r"production repository enabled",
        r"route switch authorized",
        r"fallback removal authorized",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ]
    for pattern in forbidden_patterns:
        if re.search(pattern, text):
            blockers.append(f"doc appears to claim forbidden state: {pattern}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def build_report() -> dict[str, Any]:
    data = load_yaml()
    checks = {
        "required_docs": check_required_docs(),
        "authorizations": check_authorizations(data),
        "migration_scope": check_migration_scope(data),
        "tables": check_tables(data),
        "business_continuity": check_business_continuity(data),
        "migration_artifacts": check_migration_artifacts(),
        "change_scope": check_change_scope(),
        "no_destructive_sql": check_no_destructive_sql(),
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
        "# Phase 4AD Action Templates Companion Migration Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4AD action templates companion migration readiness.")
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
