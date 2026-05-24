#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN_MD = ROOT / "docs/development/phase_4e_profile_segment_template_repository_adapter_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4e_profile_segment_template_repository_adapter_plan.yaml"
LEGACY_ROUTES = ROOT / "wecom_ability_service/http/automation_conversion.py"
REQUIRED_DOCS = [
    PLAN_MD,
    PLAN_YAML,
    ROOT / "docs/development/phase_4d_profile_segment_template_production_switch_plan.md",
    ROOT / "docs/development/phase_4c_profile_segment_template_native_contract.md",
    ROOT / "docs/development/phase_4b_profile_segment_template_implementation_plan.md",
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
EXPECTED_ROUTES = {
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/catalog"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/options"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/{template_id}"),
    ("POST", "/api/admin/automation-conversion/profile-segment-templates"),
    ("PUT", "/api/admin/automation-conversion/profile-segment-templates/{template_id}"),
}
LEGACY_ROUTE_CHECKS = [
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/catalog"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/options"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/<int:template_id>"),
    ("POST", "/api/admin/automation-conversion/profile-segment-templates"),
    ("PUT", "/api/admin/automation-conversion/profile-segment-templates/<int:template_id>"),
]
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
}
REQUIRED_STRATEGIES = {"reuse_legacy_tables", "legacy_service_adapter", "new_next_tables"}
REQUIRED_METHODS = {
    "list_profile_segment_templates",
    "get_profile_segment_template",
    "create_profile_segment_template",
    "update_profile_segment_template",
    "list_catalog",
    "list_options",
}
REQUIRED_PARITY = {
    "read_parity",
    "validation_parity",
    "create_dry_run_or_shadow_parity",
    "update_dry_run_or_shadow_parity",
    "error_shape_parity",
    "audit_rollback_parity",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4e_profile_segment_template_repository_adapter_plan.md",
    "docs/development/phase_4e_profile_segment_template_repository_adapter_plan.yaml",
    "docs/development/phase_4f_profile_segment_template_schema_confirmation.md",
    "docs/development/phase_4f_profile_segment_template_schema_confirmation.yaml",
    "docs/development/phase_4g_profile_segment_template_companion_schema_plan.md",
    "docs/development/phase_4g_profile_segment_template_companion_schema_plan.yaml",
    "tools/check_phase4a_internal_write_candidate_selection.py",
    "tools/check_phase4b_profile_segment_template_plan.py",
    "tools/check_phase4c_profile_segment_template_native_contract.py",
    "tools/check_phase4d_profile_segment_template_production_switch_plan.py",
    "tools/check_phase4e_profile_segment_template_repository_adapter_plan.py",
    "tools/check_phase4f_profile_segment_template_schema_confirmation.py",
    "tools/check_phase4g_profile_segment_template_companion_schema_plan.py",
    "tests/test_phase4e_profile_segment_template_repository_adapter_plan.py",
    "tests/test_phase4f_profile_segment_template_schema_confirmation.py",
    "tests/test_phase4g_profile_segment_template_companion_schema_plan.py",
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
    if data.get("status") != "phase_4e_repository_adapter_planning_only_no_runtime_change":
        blockers.append("status must be phase_4e_repository_adapter_planning_only_no_runtime_change")
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


def check_legacy_discovery(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    discovery = data.get("legacy_discovery") or {}
    blockers: list[str] = []
    if discovery.get("status") not in {"documented", "needs_confirmation"}:
        blockers.append("legacy_discovery.status must be documented or needs_confirmation")
    registered = {
        (str(item.get("method") or "").upper(), str(item.get("path") or ""))
        for item in _as_list(discovery.get("route_registration"))
        if isinstance(item, dict)
    }
    missing = sorted(EXPECTED_ROUTES - registered)
    if missing:
        blockers.append(f"legacy_discovery route_registration missing: {missing}")
    if not _as_list(discovery.get("controllers")):
        blockers.append("legacy_discovery controllers missing")
    if not _as_list(discovery.get("services")) and discovery.get("status") != "needs_confirmation":
        blockers.append("legacy_discovery services missing")
    persistence = discovery.get("persistence") or {}
    if not persistence.get("status"):
        blockers.append("legacy_discovery.persistence.status missing")
    if not _as_list(persistence.get("tables")) and discovery.get("status") != "needs_confirmation":
        blockers.append("legacy_discovery.persistence.tables missing")
    if discovery.get("status") == "needs_confirmation" and not _as_list(persistence.get("unknowns")):
        blockers.append("legacy_discovery needs_confirmation requires unknowns")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_field_mapping(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    fields = {str(item.get("next_field") or "") for item in _as_list(data.get("field_mapping")) if isinstance(item, dict)}
    missing = sorted(REQUIRED_NEXT_FIELDS - fields)
    blockers = [f"field_mapping missing {missing}"] if missing else []
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_repository_strategy(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    strategy = data.get("repository_strategy") or {}
    options = {str(item.get("id") or ""): item for item in _as_list(strategy.get("options")) if isinstance(item, dict)}
    blockers: list[str] = []
    missing = sorted(REQUIRED_STRATEGIES - set(options))
    if missing:
        blockers.append(f"repository_strategy missing options {missing}")
    if not strategy.get("selected_strategy") and not strategy.get("selection_status"):
        blockers.append("repository_strategy requires selected_strategy or selection_status")
    new_next = options.get("new_next_tables") or {}
    recommendation = str(new_next.get("recommendation") or "").lower()
    risks = " ".join(str(item).lower() for item in _as_list(new_next.get("risks")))
    if "first" in recommendation and "reuse" not in risks:
        blockers.append("new_next_tables must not be recommended as first step unless reuse impossibility is documented")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_repository_contract(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    contract = data.get("planned_repository_contract") or {}
    methods = {str(item.get("name") or ""): item for item in _as_list(contract.get("methods")) if isinstance(item, dict)}
    blockers: list[str] = []
    missing = sorted(REQUIRED_METHODS - set(methods))
    if missing:
        blockers.append(f"planned_repository_contract missing methods {missing}")
    create = methods.get("create_profile_segment_template") or {}
    if create:
        for field in ("transaction_required", "idempotency_required", "audit_required", "rollback_required"):
            if create.get(field) is not True:
                blockers.append(f"create_profile_segment_template {field} must be true")
        if not create.get("validation_boundary"):
            blockers.append("create_profile_segment_template validation_boundary missing")
    update = methods.get("update_profile_segment_template") or {}
    if update:
        for field in ("transaction_required", "audit_required", "rollback_required"):
            if update.get(field) is not True:
                blockers.append(f"update_profile_segment_template {field} must be true")
        if not update.get("validation_boundary"):
            blockers.append("update_profile_segment_template validation_boundary missing")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_designs_and_parity(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if (data.get("idempotency_design") or {}).get("required") is not True:
        blockers.append("idempotency_design.required must be true")
    if (data.get("audit_design") or {}).get("required") is not True:
        blockers.append("audit_design.required must be true")
    rollback = data.get("rollback_design") or {}
    if rollback.get("required") is not True:
        blockers.append("rollback_design.required must be true")
    if rollback.get("backup_required_if_db_write") is not True:
        blockers.append("rollback_design.backup_required_if_db_write must be true")
    parity = set(_as_list((data.get("parity_plan") or {}).get("required")))
    missing = sorted(REQUIRED_PARITY - parity)
    if missing:
        blockers.append(f"parity_plan missing {missing}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4f_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    recommendation = data.get("phase_4f_recommendation") or {}
    blockers: list[str] = []
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_4f_recommendation.recommended_next_step missing")
    for field in (
        "direct_route_switch_allowed",
        "production_repository_allowed_without_owner_approval",
        "migration_allowed_without_owner_approval",
    ):
        if recommendation.get(field) is not False:
            blockers.append(f"phase_4f_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_legacy_route_registration() -> dict[str, Any]:
    text = _read(LEGACY_ROUTES)
    blockers: list[str] = []
    for method, path in LEGACY_ROUTE_CHECKS:
        if path not in text or f'methods=["{method}"]' not in text:
            blockers.append(f"legacy route not registered for {method} {path}")
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
        blockers.append(f"unexpected changed files outside Phase 4E planning scope: {unexpected}")
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
        "legacy_discovery": check_legacy_discovery(data),
        "field_mapping": check_field_mapping(data),
        "repository_strategy": check_repository_strategy(data),
        "repository_contract": check_repository_contract(data),
        "designs_and_parity": check_designs_and_parity(data),
        "phase4f_recommendation": check_phase4f_recommendation(data),
        "legacy_route_registration": check_legacy_route_registration(),
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
        "# Phase 4E Profile Segment Template Repository Adapter Plan Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4E profile segment repository adapter planning guardrails.")
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
