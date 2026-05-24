#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN_MD = ROOT / "docs/development/phase_4d_profile_segment_template_production_switch_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4d_profile_segment_template_production_switch_plan.yaml"
LEGACY_ROUTES = ROOT / "wecom_ability_service/http/automation_conversion.py"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
REQUIRED_DOCS = [
    PLAN_MD,
    PLAN_YAML,
    ROOT / "docs/development/phase_4c_profile_segment_template_native_contract.md",
    ROOT / "docs/development/phase_4b_profile_segment_template_implementation_plan.md",
    ROOT / "docs/development/phase_4a_internal_write_candidate_selection.md",
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
REQUIRED_FORBIDDEN_SCOPE = {
    "delete",
    "run_due",
    "automation_execution",
    "outbound_send",
    "wecom_external_call",
    "openclaw_call",
    "mcp_real_call",
    "timer",
    "workflow_activation",
    "customer_pool_state_change",
    "fallback_removal",
}
EXPECTED_ROUTES = {
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/catalog"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/options"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/{template_id}"),
    ("POST", "/api/admin/automation-conversion/profile-segment-templates"),
    ("PUT", "/api/admin/automation-conversion/profile-segment-templates/{template_id}"),
}
REQUIRED_ROUTE_SEQUENCE = [
    "keep_production_compat_owner",
    "implement_or_plan_production_repository",
    "parity_check",
    "read_only_flag",
    "write_flag",
    "narrow_production_compat_later",
]
REQUIRED_PARITY = {
    "list_parity",
    "detail_parity",
    "catalog_options_parity",
    "validation_error_parity",
    "idempotency_behavior_check",
    "audit_rollback_check",
}
REQUIRED_SMOKE = {
    "read_catalog",
    "read_list",
    "read_options",
    "read_detail",
    "create_dry_run_or_safe_namespace",
    "update_dry_run_or_safe_template",
    "invalid_payload_rejected",
    "dangerous_fields_rejected",
    "no_external_side_effect",
    "fallback_available",
}
REQUIRED_ROLLBACK = {
    "route_owner_rollback_to_production_compat",
    "feature_flag_disable_if_later_added",
    "data_rollback_path",
    "audit_review",
    "backup_or_snapshot_if_db_write",
    "rollback_owner_on_call",
}
LEGACY_ROUTE_CHECKS = [
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/catalog"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/options"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/<int:template_id>"),
    ("POST", "/api/admin/automation-conversion/profile-segment-templates"),
    ("PUT", "/api/admin/automation-conversion/profile-segment-templates/<int:template_id>"),
]
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4d_profile_segment_template_production_switch_plan.md",
    "docs/development/phase_4d_profile_segment_template_production_switch_plan.yaml",
    "docs/development/phase_4e_profile_segment_template_repository_adapter_plan.md",
    "docs/development/phase_4e_profile_segment_template_repository_adapter_plan.yaml",
    "docs/development/phase_4f_profile_segment_template_schema_confirmation.md",
    "docs/development/phase_4f_profile_segment_template_schema_confirmation.yaml",
    "tools/check_phase4a_internal_write_candidate_selection.py",
    "tools/check_phase4b_profile_segment_template_plan.py",
    "tools/check_phase4c_profile_segment_template_native_contract.py",
    "tools/check_phase4d_profile_segment_template_production_switch_plan.py",
    "tools/check_phase4e_profile_segment_template_repository_adapter_plan.py",
    "tools/check_phase4f_profile_segment_template_schema_confirmation.py",
    "tests/test_phase4d_profile_segment_template_production_switch_plan.py",
    "tests/test_phase4e_profile_segment_template_repository_adapter_plan.py",
    "tests/test_phase4f_profile_segment_template_schema_confirmation.py",
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


def check_plan_yaml(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if data.get("status") != "phase_4d_planning_only_no_runtime_change":
        blockers.append("status must be phase_4d_planning_only_no_runtime_change")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    if data.get("route_family") != EXPECTED_ROUTE_FAMILY:
        blockers.append("route_family mismatch")
    if data.get("capability_owner") != EXPECTED_CAPABILITY_OWNER:
        blockers.append("capability_owner mismatch")
    if data.get("integration_fallback_boundary") != EXPECTED_FALLBACK_BOUNDARY:
        blockers.append("integration_fallback_boundary mismatch")

    scope = data.get("scope") or {}
    forbidden = set(_as_list(scope.get("forbidden")))
    missing_forbidden = sorted(REQUIRED_FORBIDDEN_SCOPE - forbidden)
    if missing_forbidden:
        blockers.append(f"missing forbidden scope: {missing_forbidden}")
    routes = {
        (str(item.get("method") or "").upper(), str(item.get("path") or ""))
        for item in _as_list(scope.get("planned_routes"))
        if isinstance(item, dict)
    }
    missing_routes = sorted(EXPECTED_ROUTES - routes)
    if missing_routes:
        blockers.append(f"missing planned routes: {missing_routes}")

    strategy = data.get("repository_strategy") or {}
    options = _as_list(strategy.get("options"))
    option_by_id = {str(item.get("id") or ""): item for item in options if isinstance(item, dict)}
    for option_id in ("reuse_legacy_tables", "new_next_tables"):
        option = option_by_id.get(option_id)
        if not option:
            blockers.append(f"repository_strategy missing option {option_id}")
            continue
        for field in ("pros", "cons", "risks"):
            if not _as_list(option.get(field)):
                blockers.append(f"{option_id} missing {field}")
    if not strategy.get("selected_strategy") and strategy.get("selection_status") != "pending_owner_approval":
        blockers.append("selected_strategy must be non-empty or selection_status must be pending_owner_approval")

    ownership = data.get("route_ownership_strategy") or {}
    if ownership.get("production_switch_in_phase_4d") is not False:
        blockers.append("production_switch_in_phase_4d must be false")
    if ownership.get("fallback_retained") is not True:
        blockers.append("fallback_retained must be true")
    sequence = _as_list(ownership.get("recommended_sequence"))
    for item in REQUIRED_ROUTE_SEQUENCE:
        if item not in sequence:
            blockers.append(f"route ownership sequence missing {item}")

    parity = data.get("parity_plan") or {}
    missing_parity = sorted(REQUIRED_PARITY - set(_as_list(parity.get("required"))))
    if missing_parity:
        blockers.append(f"parity_plan missing {missing_parity}")
    if parity.get("write_dual_run_authorized") is not False:
        blockers.append("write_dual_run_authorized must be false")

    smoke = data.get("production_smoke_plan") or {}
    missing_smoke = sorted(REQUIRED_SMOKE - set(_as_list(smoke.get("required"))))
    if missing_smoke:
        blockers.append(f"production_smoke_plan missing {missing_smoke}")

    rollback = data.get("rollback_plan") or {}
    missing_rollback = sorted(REQUIRED_ROLLBACK - set(_as_list(rollback.get("required"))))
    if missing_rollback:
        blockers.append(f"rollback_plan missing {missing_rollback}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_legacy_route_registration() -> dict[str, Any]:
    text = _read(LEGACY_ROUTES)
    blockers: list[str] = []
    for method, path in LEGACY_ROUTE_CHECKS:
        if path not in text or f'methods=["{method}"]' not in text:
            blockers.append(f"legacy route not registered for {method} {path}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_production_compat_fallback() -> dict[str, Any]:
    text = _read(PRODUCTION_COMPAT)
    blockers: list[str] = []
    for snippet in (
        '"/api/admin/automation-conversion/profile-segment-templates"',
        '"/api/admin/automation-conversion/profile-segment-templates/{path:path}"',
        "legacy_automation_workspace_routes",
        "forward_to_legacy_flask",
    ):
        if snippet not in text:
            blockers.append(f"production_compat fallback missing snippet: {snippet}")
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
        blockers.append(f"unexpected changed files outside Phase 4D planning scope: {unexpected}")
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
        "plan_yaml": check_plan_yaml(data),
        "legacy_route_registration": check_legacy_route_registration(),
        "production_compat_fallback": check_production_compat_fallback(),
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
        "# Phase 4D Profile Segment Template Production Switch Plan Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4D profile segment template production switch planning guardrails.")
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
