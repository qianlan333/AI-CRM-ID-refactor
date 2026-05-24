#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN_MD = ROOT / "docs/development/phase_4f_profile_segment_template_schema_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4f_profile_segment_template_schema_confirmation.yaml"
SCHEMA_SQL = ROOT / "wecom_ability_service/schema_postgres.sql"
MIGRATIONS = ROOT / "wecom_ability_service/db/migrations/postgres_migrations.py"
WORKFLOW_SERVICE = ROOT / "wecom_ability_service/domains/automation_conversion/workflow_service.py"
REQUIRED_DOCS = [
    PLAN_MD,
    PLAN_YAML,
    ROOT / "docs/development/phase_4e_profile_segment_template_repository_adapter_plan.md",
    ROOT / "docs/development/phase_4d_profile_segment_template_production_switch_plan.md",
    ROOT / "docs/development/phase_4c_profile_segment_template_native_contract.md",
]
AUTH_FALSE_FIELDS = {
    "production_repository_implementation_authorized",
    "migration_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
EXPECTED_ROUTE_FAMILY = "/api/admin/automation-conversion/profile-segment-templates*"
EXPECTED_CAPABILITY_OWNER = "aicrm_next.automation_engine"
EXPECTED_FALLBACK_BOUNDARY = "aicrm_next.integration_gateway"
REQUIRED_TABLES = {
    "automation_profile_segment_template",
    "automation_profile_segment_category",
    "automation_profile_segment_option_mapping",
}
REQUIRED_SERVICES = {
    "list_conversion_profile_segment_catalog",
    "list_conversion_profile_segment_templates",
    "list_conversion_profile_segment_template_options",
    "get_conversion_profile_segment_template_bundle",
    "create_conversion_profile_segment_template",
    "update_conversion_profile_segment_template",
}
REQUIRED_NEXT_FIELDS = {
    "template_id / id",
    "name",
    "description",
    "segment_key / code",
    "conditions / rules",
    "status",
    "sort_order",
    "created_at",
    "updated_at",
    "operator / audit fields",
}
ALLOWED_FIELD_STATUSES = {
    "confirmed",
    "needs_owner_approval",
    "needs_migration",
    "not_supported_by_legacy_schema",
}
ALLOWED_FEASIBILITY_DECISIONS = {
    "reuse_legacy_tables_confirmed",
    "reuse_legacy_tables_needs_companion_idempotency_audit",
    "schema_insufficient_requires_migration_plan",
    "needs_more_discovery",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4f_profile_segment_template_schema_confirmation.md",
    "docs/development/phase_4f_profile_segment_template_schema_confirmation.yaml",
    "docs/development/phase_4g_profile_segment_template_companion_schema_plan.md",
    "docs/development/phase_4g_profile_segment_template_companion_schema_plan.yaml",
    "docs/development/phase_4h_profile_segment_template_companion_migration.md",
    "docs/development/phase_4h_profile_segment_template_companion_migration.yaml",
    "tools/check_phase4b_profile_segment_template_plan.py",
    "tools/check_phase4c_profile_segment_template_native_contract.py",
    "tools/check_phase4d_profile_segment_template_production_switch_plan.py",
    "tools/check_phase4e_profile_segment_template_repository_adapter_plan.py",
    "tools/check_phase4f_profile_segment_template_schema_confirmation.py",
    "tools/check_phase4g_profile_segment_template_companion_schema_plan.py",
    "tools/check_phase4h_profile_segment_template_companion_migration.py",
    "tests/test_phase4f_profile_segment_template_schema_confirmation.py",
    "tests/test_phase4g_profile_segment_template_companion_schema_plan.py",
    "tests/test_phase4h_profile_segment_template_companion_migration.py",
    "wecom_ability_service/schema_postgres.sql",
    "wecom_ability_service/db/migrations/postgres_migrations.py",
}
PROTECTED_PREFIXES = (
    "aicrm_next/",
    "wecom_ability_service/",
    "migrations/",
    "deploy",
    "systemd",
    "nginx",
)
PROTECTED_EXACT = {"app.py", "legacy_flask_app.py"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
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


def _run_git(args: list[str]) -> tuple[bool, set[str], str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return False, set(), (proc.stderr or proc.stdout).strip()
    return True, {line.strip() for line in proc.stdout.splitlines() if line.strip()}, ""


def _changed_files_from_git() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only", "--cached"]):
        ok, files, error = _run_git(args)
        if ok:
            changed.update(files)
        else:
            warnings.append(f"git {' '.join(args)} unavailable: {error}")
    ok, files, error = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(files)
    else:
        warnings.append(f"git ls-files --others unavailable: {error}")
    return changed, warnings


def check_required_docs() -> dict[str, Any]:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_DOCS if not path.exists()]
    return {"ok": not missing, "blockers": [f"missing required doc: {path}" for path in missing], "warnings": []}


def check_top_level(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if data.get("status") != "phase_4f_schema_confirmation_only_no_runtime_change":
        blockers.append("status must be phase_4f_schema_confirmation_only_no_runtime_change")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    if data.get("route_family") != EXPECTED_ROUTE_FAMILY:
        blockers.append("route_family mismatch")
    if data.get("capability_owner") != EXPECTED_CAPABILITY_OWNER:
        blockers.append("capability_owner mismatch")
    if data.get("integration_fallback_boundary") != EXPECTED_FALLBACK_BOUNDARY:
        blockers.append("integration_fallback_boundary mismatch")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_confirmed_tables(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    tables = {str(item.get("name") or ""): item for item in _as_list(data.get("confirmed_tables")) if isinstance(item, dict)}
    blockers: list[str] = []
    missing = sorted(REQUIRED_TABLES - set(tables))
    if missing:
        blockers.append(f"confirmed_tables missing {missing}")
    for name, item in tables.items():
        if name not in REQUIRED_TABLES:
            continue
        for field in ("schema_source", "primary_key", "timestamp_behavior", "status"):
            if not item.get(field):
                blockers.append(f"{name} missing {field}")
        if not _as_list(item.get("required_fields")):
            blockers.append(f"{name} missing required_fields")
        if not _as_list(item.get("unknowns")):
            blockers.append(f"{name} missing unknowns")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_confirmed_services(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    services = {
        str(item.get("function") or ""): item
        for item in _as_list(data.get("confirmed_services"))
        if isinstance(item, dict)
    }
    blockers: list[str] = []
    missing = sorted(REQUIRED_SERVICES - set(services))
    if missing:
        blockers.append(f"confirmed_services missing {missing}")
    required_fields = (
        "file",
        "behavior",
        "validation",
        "transaction_behavior",
        "error_behavior",
        "operator_handling",
        "rollback_implication",
    )
    for name, item in services.items():
        if name not in REQUIRED_SERVICES:
            continue
        for field in required_fields:
            if not item.get(field):
                blockers.append(f"{name} missing {field}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_field_mapping_confirmation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    fields = {
        str(item.get("next_field") or ""): item
        for item in _as_list(data.get("field_mapping_confirmation"))
        if isinstance(item, dict)
    }
    blockers: list[str] = []
    missing = sorted(REQUIRED_NEXT_FIELDS - set(fields))
    if missing:
        blockers.append(f"field_mapping_confirmation missing {missing}")
    for name, item in fields.items():
        if name not in REQUIRED_NEXT_FIELDS:
            continue
        status = str(item.get("status") or "")
        if status not in ALLOWED_FIELD_STATUSES:
            blockers.append(f"{name} has invalid status {status!r}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_idempotency_confirmation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    idem = data.get("idempotency_confirmation") or {}
    blockers: list[str] = []
    existing = idem.get("existing_storage_confirmed")
    if existing not in {True, False}:
        blockers.append("idempotency_confirmation.existing_storage_confirmed must be explicit true/false")
    if not idem.get("recommended_path"):
        blockers.append("idempotency_confirmation.recommended_path missing")
    if not idem.get("notes"):
        blockers.append("idempotency_confirmation.notes missing")
    if existing is not True and idem.get("phase_4g_blocker_if_unresolved") is not True:
        blockers.append("idempotency unresolved must block Phase 4G")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_audit_confirmation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    audit = data.get("audit_confirmation") or {}
    blockers: list[str] = []
    if audit.get("operator_snapshot_confirmed") is not True:
        blockers.append("audit_confirmation.operator_snapshot_confirmed must be true")
    for field in ("dedicated_audit_storage_confirmed", "before_after_snapshot_storage_confirmed"):
        if audit.get(field) not in {True, False}:
            blockers.append(f"audit_confirmation.{field} must be explicit true/false")
    if not audit.get("recommended_path"):
        blockers.append("audit_confirmation.recommended_path missing")
    if not audit.get("notes"):
        blockers.append("audit_confirmation.notes missing")
    full_audit = (
        audit.get("operator_snapshot_confirmed") is True
        and audit.get("dedicated_audit_storage_confirmed") is True
        and audit.get("before_after_snapshot_storage_confirmed") is True
    )
    if not full_audit and audit.get("phase_4g_blocker_if_unresolved") is not True:
        blockers.append("incomplete audit storage must block Phase 4G")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_repository_adapter_feasibility(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    feasibility = data.get("repository_adapter_feasibility") or {}
    blockers: list[str] = []
    decision = str(feasibility.get("decision") or "")
    if decision not in ALLOWED_FEASIBILITY_DECISIONS:
        blockers.append(f"repository_adapter_feasibility.decision invalid: {decision!r}")
    if feasibility.get("production_adapter_implementation_allowed_next") is not False:
        blockers.append("production_adapter_implementation_allowed_next must be false")
    if feasibility.get("owner_approval_required") is not True:
        blockers.append("owner_approval_required must be true")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4g_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    recommendation = data.get("phase_4g_recommendation") or {}
    blockers: list[str] = []
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_4g_recommendation.recommended_next_step missing")
    for field in (
        "direct_route_switch_allowed",
        "production_route_owner_switch_allowed",
        "production_repository_allowed_without_owner_approval",
        "migration_allowed_without_owner_approval",
    ):
        if recommendation.get(field) is not False:
            blockers.append(f"phase_4g_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_source_crosscheck(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    decision = str((data.get("repository_adapter_feasibility") or {}).get("decision") or "")
    allow_missing = decision == "needs_more_discovery"
    schema_text = _read(SCHEMA_SQL) + "\n" + (_read(MIGRATIONS) if MIGRATIONS.exists() else "")
    service_text = _read(WORKFLOW_SERVICE)
    blockers: list[str] = []
    for table in sorted(REQUIRED_TABLES):
        if table not in schema_text and not allow_missing:
            blockers.append(f"table missing from schema/migration source: {table}")
    for service in sorted(REQUIRED_SERVICES):
        if f"def {service}" not in service_text and not allow_missing:
            blockers.append(f"service missing from workflow_service.py: {service}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected_runtime_file(path: str) -> bool:
    if path in PROTECTED_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_no_runtime_changes() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected_runtime_file(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4F schema confirmation scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_doc_claims() -> dict[str, Any]:
    text = _read(PLAN_MD).lower()
    blockers: list[str] = []
    forbidden_claims = [
        "production repository implemented",
        "migration authorized",
        "production ownership switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ]
    for claim in forbidden_claims:
        if re.search(rf"(?<!not ){re.escape(claim)}", text):
            blockers.append(f"doc appears to claim forbidden state: {claim}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def build_report() -> dict[str, Any]:
    data = load_yaml()
    checks = {
        "required_docs": check_required_docs(),
        "top_level": check_top_level(data),
        "confirmed_tables": check_confirmed_tables(data),
        "confirmed_services": check_confirmed_services(data),
        "field_mapping_confirmation": check_field_mapping_confirmation(data),
        "idempotency_confirmation": check_idempotency_confirmation(data),
        "audit_confirmation": check_audit_confirmation(data),
        "repository_adapter_feasibility": check_repository_adapter_feasibility(data),
        "phase4g_recommendation": check_phase4g_recommendation(data),
        "source_crosscheck": check_source_crosscheck(data),
        "no_runtime_changes": check_no_runtime_changes(),
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
        "# Phase 4F Profile Segment Template Schema Confirmation Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4F profile segment schema confirmation guardrails.")
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
