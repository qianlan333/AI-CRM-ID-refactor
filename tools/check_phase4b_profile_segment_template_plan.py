#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN_MD = ROOT / "docs/development/phase_4b_profile_segment_template_implementation_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4b_profile_segment_template_implementation_plan.yaml"
LEGACY_AUTOMATION_ROUTES = ROOT / "wecom_ability_service/http/automation_conversion.py"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
REQUIRED_DOCS = [
    PLAN_MD,
    PLAN_YAML,
    ROOT / "docs/development/phase_4a_internal_write_candidate_selection.md",
    ROOT / "docs/development/phase_4a_internal_write_candidate_selection.yaml",
]
AUTH_FALSE_FIELDS = {
    "implementation_authorized",
    "production_cutover_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "db_schema_change_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
EXPECTED_ROUTE_FAMILY = "/api/admin/automation-conversion/profile-segment-templates*"
EXPECTED_CAPABILITY_OWNER = "aicrm_next.automation_engine"
EXPECTED_FALLBACK_BOUNDARY = "aicrm_next.integration_gateway"
REQUIRED_FORBIDDEN_SCOPE = {
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
WRITE_ROUTE_KEYS = {
    ("POST", "/api/admin/automation-conversion/profile-segment-templates"),
    ("PUT", "/api/admin/automation-conversion/profile-segment-templates/{template_id}"),
}
REQUIRED_GUARDRAILS = {
    "idempotency_required",
    "audit_operator_identity_required",
    "validation_required",
    "rollback_required",
    "fallback_retained",
    "production_compat_unchanged",
    "checker_required",
    "smoke_required",
    "fixture_success_forbidden",
    "no_real_external_side_effect",
}
REQUIRED_ENTRY_CONDITIONS = {
    "owner_approval_required",
    "checker_required",
    "smoke_required",
    "rollback_owner_required",
    "production_config_review_required",
}
REQUIRED_SIGNOFF_PENDING = {
    "automation_engine_owner",
    "integration_gateway_owner",
    "business_owner",
    "rollback_owner",
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
    "docs/development/phase_4b_profile_segment_template_implementation_plan.md",
    "docs/development/phase_4b_profile_segment_template_implementation_plan.yaml",
    "tools/check_phase4a_internal_write_candidate_selection.py",
    "tools/check_phase4b_profile_segment_template_plan.py",
    "tests/test_phase4b_profile_segment_template_plan.py",
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


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
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
        if not stripped.strip():
            continue
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


def check_required_docs() -> dict[str, Any]:
    blockers = [f"{_rel(path)} missing" for path in REQUIRED_DOCS if not path.exists()]
    return {"ok": not blockers, "blockers": blockers}


def check_plan_yaml() -> dict[str, Any]:
    blockers: list[str] = []
    if not PLAN_YAML.exists():
        return {"ok": False, "blockers": [f"{_rel(PLAN_YAML)} missing"], "routes": []}
    data = load_yaml()
    if data.get("version") != 1:
        blockers.append("version must be 1")
    if data.get("status") != "phase_4b_planning_only_no_runtime_change":
        blockers.append("status must be phase_4b_planning_only_no_runtime_change")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    if data.get("route_family") != EXPECTED_ROUTE_FAMILY:
        blockers.append(f"route_family must be {EXPECTED_ROUTE_FAMILY}")
    if data.get("capability_owner") != EXPECTED_CAPABILITY_OWNER:
        blockers.append(f"capability_owner must be {EXPECTED_CAPABILITY_OWNER}")
    if data.get("integration_fallback_boundary") != EXPECTED_FALLBACK_BOUNDARY:
        blockers.append(f"integration_fallback_boundary must be {EXPECTED_FALLBACK_BOUNDARY}")

    scope = data.get("phase_4c_scope") or {}
    forbidden_scope = {str(item) for item in _as_list(scope.get("forbidden"))}
    missing_scope = sorted(REQUIRED_FORBIDDEN_SCOPE - forbidden_scope)
    if missing_scope:
        blockers.append(f"phase_4c_scope.forbidden missing {missing_scope}")

    routes = [item for item in _as_list(data.get("routes")) if isinstance(item, dict)]
    route_keys = {(str(route.get("method")), str(route.get("path"))) for route in routes}
    if route_keys != EXPECTED_ROUTES:
        blockers.append(f"routes mismatch expected={sorted(EXPECTED_ROUTES)} actual={sorted(route_keys)}")
    for route in routes:
        key = (str(route.get("method")), str(route.get("path")))
        label = f"{key[0]} {key[1]}"
        if route.get("external_side_effect_allowed") is not False:
            blockers.append(f"{label} external_side_effect_allowed must be false")
        if key in WRITE_ROUTE_KEYS:
            for field in ("idempotency_required", "audit_required", "rollback_required"):
                if route.get(field) is not True:
                    blockers.append(f"{label} {field} must be true")

    guardrails = data.get("required_guardrails") or {}
    for field in sorted(REQUIRED_GUARDRAILS):
        if guardrails.get(field) is not True:
            blockers.append(f"required_guardrails.{field} must be true")

    entry_conditions = data.get("phase_4c_entry_conditions") or {}
    for field in sorted(REQUIRED_ENTRY_CONDITIONS):
        if entry_conditions.get(field) is not True:
            blockers.append(f"phase_4c_entry_conditions.{field} must be true")

    signoff = data.get("owner_signoff") or {}
    for field in sorted(REQUIRED_SIGNOFF_PENDING):
        if signoff.get(field) != "pending":
            blockers.append(f"owner_signoff.{field} must be pending")

    return {"ok": not blockers, "blockers": blockers, "routes": sorted(route_keys)}


def _legacy_route_registered(source: str, path: str, method: str) -> bool:
    escaped_path = re.escape(path)
    pattern = re.compile(
        rf"bp\.route\(\s*[\"']{escaped_path}[\"']\s*,\s*methods\s*=\s*\[[^\]]*[\"']{method}[\"'][^\]]*\]",
        re.MULTILINE,
    )
    return bool(pattern.search(source))


def check_legacy_route_registration() -> dict[str, Any]:
    blockers: list[str] = []
    if not LEGACY_AUTOMATION_ROUTES.exists():
        return {"ok": False, "blockers": [f"{_rel(LEGACY_AUTOMATION_ROUTES)} missing"]}
    source = _read(LEGACY_AUTOMATION_ROUTES)
    for method, path in LEGACY_ROUTE_CHECKS:
        if not _legacy_route_registered(source, path, method):
            blockers.append(f"legacy route missing: {method} {path}")
    return {"ok": not blockers, "blockers": blockers}


def check_production_compat_fallback() -> dict[str, Any]:
    blockers: list[str] = []
    if not PRODUCTION_COMPAT.exists():
        return {"ok": False, "blockers": [f"{_rel(PRODUCTION_COMPAT)} missing"]}
    source = _read(PRODUCTION_COMPAT)
    required_snippets = [
        '@router.api_route("/api/admin/automation-conversion/profile-segment-templates"',
        '@router.api_route("/api/admin/automation-conversion/profile-segment-templates/{path:path}"',
        "forward_to_legacy_flask",
    ]
    for snippet in required_snippets:
        if snippet not in source:
            blockers.append(f"production_compat missing fallback snippet: {snippet}")
    return {"ok": not blockers, "blockers": blockers}


def _run_git(args: list[str]) -> tuple[bool, list[str], str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        return False, [], str(exc)
    if completed.returncode != 0:
        return False, [], completed.stderr.strip()
    return True, [line.strip() for line in completed.stdout.splitlines() if line.strip()], ""


def _changed_files_from_git() -> tuple[set[str], list[str]]:
    warnings: list[str] = []
    changed: set[str] = set()
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only", "origin/main"]):
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


def _is_protected_runtime_file(path: str) -> bool:
    if path in PROTECTED_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_no_runtime_changes() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if _is_protected_runtime_file(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4B planning scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def build_report() -> dict[str, Any]:
    checks = {
        "required_docs": check_required_docs(),
        "plan_yaml": check_plan_yaml(),
        "legacy_route_registration": check_legacy_route_registration(),
        "production_compat_fallback": check_production_compat_fallback(),
        "no_runtime_changes": check_no_runtime_changes(),
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
        "# Phase 4B Profile Segment Template Plan Check",
        "",
        f"- overall: {report['overall']}",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers") or []
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Warnings")
    warnings = report.get("warnings") or []
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
