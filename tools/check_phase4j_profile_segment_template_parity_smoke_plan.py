#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN_MD = ROOT / "docs/development/phase_4j_profile_segment_template_parity_smoke_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4j_profile_segment_template_parity_smoke_plan.yaml"
REQUIRED_DOCS = [
    PLAN_MD,
    PLAN_YAML,
    ROOT / "docs/development/phase_4i_profile_segment_template_repository_adapter.md",
    ROOT / "docs/development/phase_4h_profile_segment_template_companion_migration.md",
]
AUTH_FALSE_FIELDS = {
    "production_repository_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "production_smoke_execution_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
READ_PARITY = {"catalog", "list", "options", "detail"}
WRITE_PARITY = {
    "create_validation",
    "create_idempotency_replay",
    "create_idempotency_conflict",
    "create_duplicate_template",
    "update_validation",
    "update_missing_template",
    "update_before_after_snapshot",
    "update_child_replacement",
    "audit_log_shape",
    "rollback_payload_shape",
}
REQUIRED_SQL_FLAGS = {
    "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND",
    "PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND",
}
REQUIRED_DB_FLAGS = {
    "AICRM_PROFILE_SEGMENT_TEMPLATE_DATABASE_URL",
    "AICRM_NEXT_TEST_DATABASE_URL",
}
OWNER_FIELDS = {
    "automation_engine_owner",
    "integration_gateway_owner",
    "business_owner",
    "db_config_owner",
    "rollback_owner",
    "smoke_operator",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4j_profile_segment_template_parity_smoke_plan.md",
    "docs/development/phase_4j_profile_segment_template_parity_smoke_plan.yaml",
    "tools/check_phase4j_profile_segment_template_parity_smoke_plan.py",
    "tests/test_phase4j_profile_segment_template_parity_smoke_plan.py",
    "tools/check_phase4i_profile_segment_template_repository_adapter.py",
    "tools/check_phase4h_profile_segment_template_companion_migration.py",
    "docs/development/phase_4k_profile_segment_template_local_parity_harness.md",
    "docs/development/phase_4k_profile_segment_template_local_parity_harness.yaml",
    "tools/run_phase4k_profile_segment_template_local_parity.py",
    "tools/check_phase4k_profile_segment_template_local_parity_harness.py",
    "tests/test_phase4k_profile_segment_template_local_parity_harness.py",
    "docs/development/phase_4l_profile_segment_template_staging_smoke_plan.md",
    "docs/development/phase_4l_profile_segment_template_staging_smoke_plan.yaml",
    "tools/check_phase4l_profile_segment_template_staging_smoke_plan.py",
    "tests/test_phase4l_profile_segment_template_staging_smoke_plan.py",
    "tools/run_phase4m_profile_segment_template_staging_smoke.py",
    "docs/development/phase_4m_profile_segment_template_staging_smoke_package.md",
    "docs/development/phase_4m_profile_segment_template_staging_smoke_package.yaml",
    "tools/check_phase4m_profile_segment_template_staging_smoke_package.py",
    "tests/test_phase4m_profile_segment_template_staging_smoke_package.py",
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
    if data.get("status") != "phase_4j_parity_smoke_planning_only_no_runtime_change":
        blockers.append("status must be phase_4j_parity_smoke_planning_only_no_runtime_change")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    if data.get("route_family") != "/api/admin/automation-conversion/profile-segment-templates*":
        blockers.append("route_family mismatch")
    if data.get("capability_owner") != "aicrm_next.automation_engine":
        blockers.append("capability_owner mismatch")
    if data.get("integration_fallback_boundary") != "aicrm_next.integration_gateway":
        blockers.append("integration_fallback_boundary mismatch")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_parity_matrix(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    matrix = data.get("parity_matrix") or {}
    blockers: list[str] = []
    read_names = {str(item.get("name") or "") for item in _as_list(matrix.get("read")) if isinstance(item, dict)}
    write_names = {str(item.get("name") or "") for item in _as_list(matrix.get("write")) if isinstance(item, dict)}
    missing_read = sorted(READ_PARITY - read_names)
    missing_write = sorted(WRITE_PARITY - write_names)
    if missing_read:
        blockers.append(f"read parity missing {missing_read}")
    if missing_write:
        blockers.append(f"write parity missing {missing_write}")
    for section in ("read", "write"):
        for item in _as_list(matrix.get(section)):
            if not isinstance(item, dict):
                continue
            for field in ("legacy_source", "next_source", "comparison_method", "acceptable_differences", "blockers"):
                if not item.get(field):
                    blockers.append(f"{section}.{item.get('name')}.{field} must be non-empty")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_smoke_levels(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    levels = _as_list(data.get("smoke_levels"))
    by_level = {int(item.get("level")): item for item in levels if isinstance(item, dict) and item.get("level") is not None}
    blockers: list[str] = []
    if set(by_level) != {0, 1, 2, 3, 4}:
        blockers.append("smoke_levels must include exactly levels 0-4")
    for level, item in by_level.items():
        if level == 0:
            if item.get("authorized_now") is not True:
                blockers.append("level 0 must be authorized_now true")
            if item.get("requires_owner_approval") is not False:
                blockers.append("level 0 must not require owner approval")
        else:
            if item.get("authorized_now") is not False:
                blockers.append(f"level {level} must not be authorized now")
            if item.get("requires_owner_approval") is not True:
                blockers.append(f"level {level} must require owner approval")
    if by_level.get(4, {}).get("authorized_now") is not False:
        blockers.append("level 4 must not be authorized now")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_feature_flags(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    flags = data.get("feature_flags") or {}
    blockers: list[str] = []
    if flags.get("default_backend") != "memory":
        blockers.append("feature_flags.default_backend must be memory")
    if not REQUIRED_SQL_FLAGS <= {str(item) for item in _as_list(flags.get("sql_backend_flags"))}:
        blockers.append("feature_flags.sql_backend_flags missing required flags")
    if not REQUIRED_DB_FLAGS <= {str(item) for item in _as_list(flags.get("database_url_flags"))}:
        blockers.append("feature_flags.database_url_flags missing required flags")
    if flags.get("production_auto_enable") is not False:
        blockers.append("feature_flags.production_auto_enable must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_safe_namespace(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    namespace = data.get("safe_namespace") or {}
    blockers: list[str] = []
    for field in ("template_code_prefix", "operator", "idempotency_key_prefix", "cleanup_strategy"):
        if not namespace.get(field):
            blockers.append(f"safe_namespace.{field} must be non-empty")
    if namespace.get("delete_required") is not False:
        blockers.append("safe_namespace.delete_required must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_owner_approval(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    approval = data.get("owner_approval") or {}
    blockers = [f"owner_approval.{field} must be pending" for field in sorted(OWNER_FIELDS) if approval.get(field) != "pending"]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4k_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    recommendation = data.get("phase_4k_recommendation") or {}
    blockers: list[str] = []
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_4k_recommendation.recommended_next_step missing")
    for field in (
        "direct_route_switch_allowed",
        "production_write_canary_allowed",
        "production_repository_enablement_without_owner_approval",
    ):
        if recommendation.get(field) is not False:
            blockers.append(f"phase_4k_recommendation.{field} must be false")
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
        blockers.append(f"unexpected changed files outside Phase 4J parity/smoke planning scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_doc_claims() -> dict[str, Any]:
    text = _read(PLAN_MD).lower()
    blockers: list[str] = []
    forbidden_patterns = [
        r"production repository enabled",
        r"production route switch authorized",
        r"smoke executed",
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
        "top_level": check_top_level(data),
        "parity_matrix": check_parity_matrix(data),
        "smoke_levels": check_smoke_levels(data),
        "feature_flags": check_feature_flags(data),
        "safe_namespace": check_safe_namespace(data),
        "owner_approval": check_owner_approval(data),
        "phase4k_recommendation": check_phase4k_recommendation(data),
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
        "# Phase 4J Profile Segment Template Parity Smoke Plan Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4J profile segment template parity/smoke planning guardrails.")
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
