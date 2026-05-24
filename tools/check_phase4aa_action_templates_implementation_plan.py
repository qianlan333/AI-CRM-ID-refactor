#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4aa_action_templates_implementation_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4aa_action_templates_implementation_plan.yaml"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    ROOT / "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.md",
    ROOT / "docs/development/legacy_replacement_backlog.yaml",
]
SOURCE_FILES = [
    ROOT / "wecom_ability_service/http/automation_conversion.py",
    ROOT / "wecom_ability_service/http/automation_conversion_templates.py",
    ROOT / "wecom_ability_service/domains/automation_conversion/action_template_service.py",
    ROOT / "wecom_ability_service/domains/automation_conversion/workflow_repo.py",
    ROOT / "wecom_ability_service/schema_postgres.sql",
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
OUT_OF_SCOPE_REQUIRED = {
    "run_due",
    "automation_execution",
    "outbound_send",
    "wecom_external_call",
    "openclaw_call",
    "mcp_real_call",
    "timer",
    "workflow_activation",
    "customer_pool_state_change",
    "agent_runtime_execution",
    "fallback_removal",
    "production_compat_narrowing",
}
GUARDRAIL_TRUE_FIELDS = {
    "idempotency_required_for_create",
    "duplicate_protection_required",
    "audit_operator_identity_required",
    "before_after_snapshot_required_for_update",
    "rollback_payload_required",
    "dangerous_fields_rejected",
    "no_real_external_side_effect",
    "no_automation_execution",
    "fallback_retained",
    "checker_required",
    "smoke_required",
}
REPOSITORY_OPTIONS = {
    "reuse_legacy_tables",
    "legacy_service_adapter",
    "new_next_tables",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4aa_action_templates_implementation_plan.md",
    "docs/development/phase_4aa_action_templates_implementation_plan.yaml",
    "tools/check_phase4aa_action_templates_implementation_plan.py",
    "tests/test_phase4aa_action_templates_implementation_plan.py",
    "tools/check_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
    "docs/development/phase_4ab_action_templates_schema_confirmation.md",
    "docs/development/phase_4ab_action_templates_schema_confirmation.yaml",
    "tools/check_phase4ab_action_templates_schema_confirmation.py",
    "tests/test_phase4ab_action_templates_schema_confirmation.py",
    "docs/development/phase_4ac_action_templates_companion_schema_plan.md",
    "docs/development/phase_4ac_action_templates_companion_schema_plan.yaml",
    "tools/check_phase4ac_action_templates_companion_schema_plan.py",
    "tests/test_phase4ac_action_templates_companion_schema_plan.py",
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


def _item_values(value: Any) -> set[str]:
    result: set[str] = set()
    for item in _as_list(value):
        if isinstance(item, dict):
            result.add(str(item.get("item", "")))
        else:
            result.add(str(item))
    return {item for item in result if item}


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


def check_legacy_discovery(data: dict[str, Any] | None = None) -> dict[str, Any]:
    discovery = (data or load_yaml()).get("legacy_discovery") or {}
    blockers: list[str] = []
    if discovery.get("status") not in {"documented", "needs_legacy_confirmation"}:
        blockers.append("legacy_discovery.status must be documented or needs_legacy_confirmation")
    if discovery.get("status") == "documented":
        if not _as_list(discovery.get("routes")):
            blockers.append("legacy_discovery.routes must be non-empty when documented")
        if not _as_list(discovery.get("services")):
            blockers.append("legacy_discovery.services must be non-empty when documented")
    persistence = discovery.get("persistence") or {}
    if persistence.get("status") not in {"documented", "needs_legacy_confirmation"}:
        blockers.append("legacy_discovery.persistence.status must be documented or needs_legacy_confirmation")
    if persistence.get("status") == "documented" and not _as_list(persistence.get("tables")):
        blockers.append("legacy_discovery.persistence.tables must be non-empty when documented")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_scope(data: dict[str, Any] | None = None) -> dict[str, Any]:
    scope = (data or load_yaml()).get("scope") or {}
    blockers: list[str] = []
    if not _item_values(scope.get("in_scope")):
        blockers.append("scope.in_scope must be non-empty")
    missing = sorted(OUT_OF_SCOPE_REQUIRED - set(_as_list(scope.get("out_of_scope"))))
    if missing:
        blockers.append(f"scope.out_of_scope missing {missing}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_native_contract(data: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = (data or load_yaml()).get("native_contract") or {}
    blockers: list[str] = []
    if contract.get("status") not in {"proposed", "needs_legacy_confirmation"}:
        blockers.append("native_contract.status must be proposed or needs_legacy_confirmation")
    fields = _as_list(contract.get("fields"))
    if not fields:
        blockers.append("native_contract.fields must be non-empty")
    for item in fields:
        if not isinstance(item, dict) or not item.get("next_field"):
            blockers.append("native_contract.fields entries must include next_field")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_guardrails(data: dict[str, Any] | None = None) -> dict[str, Any]:
    guardrails = (data or load_yaml()).get("required_guardrails") or {}
    blockers = [
        f"required_guardrails.{field} must be true"
        for field in sorted(GUARDRAIL_TRUE_FIELDS)
        if guardrails.get(field) is not True
    ]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_repository_strategy(data: dict[str, Any] | None = None) -> dict[str, Any]:
    strategy = (data or load_yaml()).get("repository_strategy") or {}
    blockers: list[str] = []
    if not strategy.get("selected_strategy") and not strategy.get("selection_status"):
        blockers.append("repository_strategy selected_strategy or selection_status must be non-empty")
    option_ids = {str(option.get("id")) for option in _as_list(strategy.get("options")) if isinstance(option, dict)}
    missing = sorted(REPOSITORY_OPTIONS - option_ids)
    if missing:
        blockers.append(f"repository_strategy.options missing {missing}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase_4ab_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = (data or load_yaml()).get("phase_4ab_recommendation") or {}
    blockers: list[str] = []
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4ab_recommendation.recommended_next_step missing")
    for field in (
        "production_write_allowed",
        "production_route_switch_allowed",
        "fallback_removal_allowed",
        "production_write_canary_allowed",
    ):
        if rec.get(field) is not False:
            blockers.append(f"phase_4ab_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_source_cross_reference(data: dict[str, Any] | None = None) -> dict[str, Any]:
    discovery_status = ((data or load_yaml()).get("legacy_discovery") or {}).get("status")
    source = "\n".join(_read(path).lower() for path in SOURCE_FILES if path.exists())
    found = any(token in source for token in ("action-template", "action_templates", "action template", "action_template"))
    blockers: list[str] = []
    if not found and discovery_status != "needs_legacy_confirmation":
        blockers.append("action-template source names not confirmed; legacy_discovery.status must be needs_legacy_confirmation")
    if found and "automation_operation_templates" not in source:
        blockers.append("source references action templates but not automation_operation_templates")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4AA scope: {unexpected}")
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
        "legacy_discovery": check_legacy_discovery(data),
        "scope": check_scope(data),
        "native_contract": check_native_contract(data),
        "guardrails": check_guardrails(data),
        "repository_strategy": check_repository_strategy(data),
        "phase_4ab_recommendation": check_phase_4ab_recommendation(data),
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
        "# Phase 4AA Action Templates Implementation Plan Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4AA action-templates implementation planning.")
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
