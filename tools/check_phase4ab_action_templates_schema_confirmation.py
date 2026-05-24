#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4ab_action_templates_schema_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4ab_action_templates_schema_confirmation.yaml"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    ROOT / "docs/development/phase_4aa_action_templates_implementation_plan.md",
    ROOT / "docs/development/phase_4aa_action_templates_implementation_plan.yaml",
]
SOURCE_FILES = [
    ROOT / "wecom_ability_service/http/automation_conversion.py",
    ROOT / "wecom_ability_service/http/automation_conversion_templates.py",
    ROOT / "wecom_ability_service/domains/automation_conversion/action_template_service.py",
    ROOT / "wecom_ability_service/domains/automation_conversion/workflow_repo.py",
    ROOT / "wecom_ability_service/schema_postgres.sql",
    ROOT / "wecom_ability_service/db/migrations/postgres_migrations.py",
]
AUTH_FALSE_FIELDS = {
    "runtime_change_authorized",
    "production_repository_authorized",
    "migration_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "delete_ready",
}
REQUIRED_SERVICES = {
    "list_action_templates",
    "create_action_template",
    "generate_action_template",
    "create_action_template_from_workflow",
}
REQUIRED_SCHEMA_FIELDS = {
    "id",
    "template_code",
    "template_name",
    "template_source",
    "category",
    "description",
    "status",
    "default_config_json",
    "ui_schema_json",
    "workflow_blueprint_json",
    "node_blueprints_json",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "archived_at",
}
REQUIRED_FIELD_MAPPINGS = {
    "id",
    "code",
    "name",
    "template_source",
    "category",
    "description",
    "status",
    "default_config",
    "ui_schema",
    "workflow_blueprint",
    "node_blueprints",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "archived_at",
}
READINESS_DECISIONS = {
    "ready_for_fixture_native_contract",
    "needs_companion_idempotency_audit_planning",
    "needs_more_legacy_confirmation",
    "defer_due_to_external_side_effect_risk",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4ab_action_templates_schema_confirmation.md",
    "docs/development/phase_4ab_action_templates_schema_confirmation.yaml",
    "tools/check_phase4ab_action_templates_schema_confirmation.py",
    "tests/test_phase4ab_action_templates_schema_confirmation.py",
    "tools/check_phase4aa_action_templates_implementation_plan.py",
    "tools/check_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
    "docs/development/phase_4ac_action_templates_companion_schema_plan.md",
    "docs/development/phase_4ac_action_templates_companion_schema_plan.yaml",
    "tools/check_phase4ac_action_templates_companion_schema_plan.py",
    "tests/test_phase4ac_action_templates_companion_schema_plan.py",
    "docs/development/phase_4ad_action_templates_companion_migration.md",
    "docs/development/phase_4ad_action_templates_companion_migration.yaml",
    "tools/check_phase4ad_action_templates_companion_migration.py",
    "tests/test_phase4ad_action_templates_companion_migration.py",
    "tools/check_phase4ac_action_templates_companion_schema_plan.py",
    "wecom_ability_service/schema_postgres.sql",
    "wecom_ability_service/db/migrations/postgres_migrations.py",
    "aicrm_next/automation_engine/api.py",
    "aicrm_next/automation_engine/application.py",
    "aicrm_next/automation_engine/dto.py",
    "aicrm_next/automation_engine/action_templates.py",
    "aicrm_next/automation_engine/action_template_repository.py",
    "docs/development/phase_4ae_action_templates_native_fixture_contract.md",
    "docs/development/phase_4ae_action_templates_native_fixture_contract.yaml",
    "tools/check_phase4ae_action_templates_native_fixture_contract.py",
    "tests/test_phase4ae_action_templates_native_fixture_contract.py",
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


def _dict_values(values: Any, key: str) -> set[str]:
    return {str(item.get(key)) for item in _as_list(values) if isinstance(item, dict) and item.get(key) is not None}


def _route_values(values: Any) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for item in _as_list(values):
        if isinstance(item, dict):
            routes.add((str(item.get("method", "")).upper(), str(item.get("path", ""))))
    return routes


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


def check_route_and_owner(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if data.get("route_family") != "/api/admin/automation-conversion/action-templates*":
        blockers.append("route_family must be /api/admin/automation-conversion/action-templates*")
    if data.get("capability_owner") != "aicrm_next.automation_engine":
        blockers.append("capability_owner must be aicrm_next.automation_engine")
    if data.get("integration_fallback_boundary") != "aicrm_next.integration_gateway":
        blockers.append("integration_fallback_boundary must be aicrm_next.integration_gateway")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_route_surface(data: dict[str, Any] | None = None) -> dict[str, Any]:
    surface = (data or load_yaml()).get("route_surface") or {}
    confirmed = _as_list(surface.get("confirmed_routes"))
    blockers: list[str] = []
    if not confirmed:
        blockers.append("route_surface.confirmed_routes must be non-empty")
    routes = _route_values(confirmed)
    for required in (
        ("GET", "/api/admin/automation-conversion/action-templates"),
        ("POST", "/api/admin/automation-conversion/action-templates"),
    ):
        if required not in routes:
            blockers.append(f"route_surface.confirmed_routes missing {required[0]} {required[1]}")
    generate = [
        route
        for route in confirmed
        if isinstance(route, dict) and str(route.get("path")) == "/api/admin/automation-conversion/action-templates/generate"
    ]
    if not generate or all(str(route.get("phase_4ac_scope_decision")) != "out_of_scope" for route in generate):
        out_routes = {str(item.get("route")) for item in _as_list(surface.get("out_of_scope")) if isinstance(item, dict)}
        if "POST /api/admin/automation-conversion/action-templates/generate" not in out_routes:
            blockers.append("generate route must be out_of_scope")
    from_workflow = [
        route
        for route in confirmed
        if isinstance(route, dict) and str(route.get("path")) == "/api/admin/automation-conversion/action-templates/from-workflow"
    ]
    if not from_workflow:
        blockers.append("from-workflow route must be documented")
    elif all(str(route.get("phase_4ac_scope_decision")) not in {"defer", "out_of_scope", "in_scope"} or not route.get("reason") for route in from_workflow):
        blockers.append("from-workflow route must be deferred or documented with reason")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_services(data: dict[str, Any] | None = None) -> dict[str, Any]:
    services = _as_list((data or load_yaml()).get("services"))
    blockers: list[str] = []
    functions = _dict_values(services, "function")
    missing = sorted(REQUIRED_SERVICES - functions)
    if missing:
        blockers.append(f"services missing {missing}")
    for service in services:
        if not isinstance(service, dict):
            continue
        function = service.get("function")
        if function in REQUIRED_SERVICES:
            if not service.get("side_effect_risk"):
                blockers.append(f"services.{function}.side_effect_risk missing")
            if not service.get("phase_4ac_scope_decision"):
                blockers.append(f"services.{function}.phase_4ac_scope_decision missing")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_schema_confirmation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = (data or load_yaml()).get("schema_confirmation") or {}
    blockers: list[str] = []
    if schema.get("table") != "automation_operation_templates":
        blockers.append("schema_confirmation.table must be automation_operation_templates")
    fields = _dict_values(schema.get("fields"), "name")
    missing = sorted(REQUIRED_SCHEMA_FIELDS - fields)
    if missing:
        blockers.append(f"schema_confirmation.fields missing {missing}")
    if not schema.get("timestamp_behavior"):
        blockers.append("schema_confirmation.timestamp_behavior missing")
    if not schema.get("status_archive_behavior"):
        blockers.append("schema_confirmation.status_archive_behavior missing")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_field_mapping(data: dict[str, Any] | None = None) -> dict[str, Any]:
    mappings = _as_list((data or load_yaml()).get("field_mapping_confirmation"))
    mapped = _dict_values(mappings, "next_field")
    missing = sorted(REQUIRED_FIELD_MAPPINGS - mapped)
    blockers = [f"field_mapping_confirmation missing {missing}"] if missing else []
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_idempotency_audit(data: dict[str, Any] | None = None) -> dict[str, Any]:
    section = (data or load_yaml()).get("idempotency_audit_confirmation") or {}
    blockers: list[str] = []
    for field in (
        "dedicated_idempotency_storage_confirmed",
        "dedicated_audit_storage_confirmed",
        "before_after_snapshot_storage_confirmed",
        "operator_snapshot_confirmed",
        "companion_schema_may_be_required",
    ):
        if field not in section:
            blockers.append(f"idempotency_audit_confirmation.{field} missing")
    if not section.get("notes"):
        blockers.append("idempotency_audit_confirmation.notes missing")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase_4ac_readiness(data: dict[str, Any] | None = None) -> dict[str, Any]:
    readiness = (data or load_yaml()).get("phase_4ac_readiness") or {}
    blockers: list[str] = []
    if readiness.get("decision") not in READINESS_DECISIONS:
        blockers.append("phase_4ac_readiness.decision must be an allowed value")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase_4ac_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = (data or load_yaml()).get("phase_4ac_recommendation") or {}
    blockers: list[str] = []
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4ac_recommendation.recommended_next_step missing")
    for field in (
        "production_write_allowed",
        "production_route_switch_allowed",
        "fallback_removal_allowed",
        "production_write_canary_allowed",
    ):
        if rec.get(field) is not False:
            blockers.append(f"phase_4ac_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_source_cross_reference(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    schema_status = ((data.get("schema_confirmation") or {}).get("status") or "")
    source_text = "\n".join(_read(path).lower() for path in SOURCE_FILES if path.exists())
    blockers: list[str] = []
    for token in (
        "api_admin_automation_conversion_action_templates",
        "api_admin_automation_conversion_action_template_generate",
        "api_admin_automation_conversion_action_template_from_workflow",
        "list_action_templates",
        "create_action_template",
        "generate_action_template",
        "create_action_template_from_workflow",
    ):
        if token.lower() not in source_text:
            blockers.append(f"source missing expected token: {token}")
    if "automation_operation_templates" not in source_text and schema_status != "needs_more_confirmation":
        blockers.append("source missing automation_operation_templates; schema_confirmation.status must be needs_more_confirmation")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4AB scope: {unexpected}")
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
        "route_and_owner": check_route_and_owner(data),
        "route_surface": check_route_surface(data),
        "services": check_services(data),
        "schema_confirmation": check_schema_confirmation(data),
        "field_mapping": check_field_mapping(data),
        "idempotency_audit": check_idempotency_audit(data),
        "phase_4ac_readiness": check_phase_4ac_readiness(data),
        "phase_4ac_recommendation": check_phase_4ac_recommendation(data),
        "source_cross_reference": check_source_cross_reference(data),
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
        "# Phase 4AB Action Templates Schema Confirmation Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4AB action-templates schema confirmation.")
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
