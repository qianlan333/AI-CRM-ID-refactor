#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4m_profile_segment_template_staging_smoke_package.md"
PLAN_YAML = ROOT / "docs/development/phase_4m_profile_segment_template_staging_smoke_package.yaml"
RUNNER = ROOT / "tools/run_phase4m_profile_segment_template_staging_smoke.py"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    RUNNER,
    ROOT / "docs/development/phase_4l_profile_segment_template_staging_smoke_plan.md",
    ROOT / "docs/development/phase_4k_profile_segment_template_local_parity_harness.md",
]
AUTH_FALSE_FIELDS = {
    "staging_smoke_execution_authorized",
    "production_data_allowed",
    "production_repository_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
REQUIRED_ENV = {
    "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL",
    "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND",
}
ALLOWED_MARKERS = {"staging", "stage", "test", "local", "dev"}
FORBIDDEN_MARKERS = {"prod", "production", "primary", "master"}
READ_CASES = {"catalog", "list", "options", "detail"}
WRITE_CASES = {
    "create_with_idempotency",
    "create_replay",
    "create_conflict",
    "duplicate_template_rejected",
    "update_existing",
    "update_missing",
    "invalid_payload_rejected",
    "dangerous_field_rejected",
    "audit_log_created",
    "rollback_payload_present",
    "side_effect_safety_false",
}
SIDE_EFFECT_FALSE_FIELDS = {
    "external_calls_allowed",
    "automation_execution_allowed",
    "outbound_send_allowed",
    "route_owner_change_allowed",
}
ALLOWED_CHANGED_FILES = {
    "tools/run_phase4m_profile_segment_template_staging_smoke.py",
    "docs/development/phase_4m_profile_segment_template_staging_smoke_package.md",
    "docs/development/phase_4m_profile_segment_template_staging_smoke_package.yaml",
    "tools/check_phase4m_profile_segment_template_staging_smoke_package.py",
    "tests/test_phase4m_profile_segment_template_staging_smoke_package.py",
    "tools/check_phase4l_profile_segment_template_staging_smoke_plan.py",
    "tools/check_phase4k_profile_segment_template_local_parity_harness.py",
    "tools/check_phase4j_profile_segment_template_parity_smoke_plan.py",
    "tools/check_phase4i_profile_segment_template_repository_adapter.py",
    "tools/check_phase4h_profile_segment_template_companion_migration.py",
    "docs/development/phase_4n_profile_segment_template_staging_smoke_approval.md",
    "docs/development/phase_4n_profile_segment_template_staging_smoke_approval.yaml",
    "tools/check_phase4n_profile_segment_template_staging_smoke_approval.py",
    "tests/test_phase4n_profile_segment_template_staging_smoke_approval.py",
    "docs/development/phase_4o_profile_segment_template_staging_smoke_evidence.md",
    "docs/development/phase_4o_profile_segment_template_staging_smoke_evidence.yaml",
    "tools/run_phase4o_profile_segment_template_staging_smoke_evidence.py",
    "tools/check_phase4o_profile_segment_template_staging_smoke_evidence.py",
    "tests/test_phase4o_profile_segment_template_staging_smoke_evidence.py",
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
FORBIDDEN_RUNNER_PATTERNS = [
    r"\bwecom_ability_service\b",
    r"\bimport\s+.*openclaw",
    r"\bfrom\s+.*openclaw",
    r"\bimport\s+.*mcp",
    r"\bfrom\s+.*mcp",
    r"\bimport\s+.*payment",
    r"\bfrom\s+.*payment",
    r"\bimport\s+.*oauth",
    r"\bfrom\s+.*oauth",
]


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


def check_top_level(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if data.get("status") != "phase_4m_staging_smoke_package_no_execution_no_production_change":
        blockers.append("status must be phase_4m_staging_smoke_package_no_execution_no_production_change")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_runner_config(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    runner = data.get("runner") or {}
    blockers: list[str] = []
    if runner.get("path") != "tools/run_phase4m_profile_segment_template_staging_smoke.py":
        blockers.append("runner.path mismatch")
    if runner.get("default_mode") != "dry_run":
        blockers.append("runner.default_mode must be dry_run")
    if runner.get("execute_writes_requires_flag") is not True:
        blockers.append("runner.execute_writes_requires_flag must be true")
    if not REQUIRED_ENV <= {str(item) for item in _as_list(runner.get("required_env"))}:
        blockers.append("runner.required_env missing required env vars")
    if "DATABASE_URL" not in {str(item) for item in _as_list(runner.get("forbidden_env_fallbacks"))}:
        blockers.append("runner.forbidden_env_fallbacks must include DATABASE_URL")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_db_url_safety(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    safety = data.get("db_url_safety") or {}
    blockers: list[str] = []
    if not ALLOWED_MARKERS <= {str(item) for item in _as_list(safety.get("allowed_markers"))}:
        blockers.append("db_url_safety.allowed_markers missing required markers")
    if not FORBIDDEN_MARKERS <= {str(item) for item in _as_list(safety.get("forbidden_markers"))}:
        blockers.append("db_url_safety.forbidden_markers missing required markers")
    if safety.get("fail_if_allowed_and_forbidden_both_present") is not True:
        blockers.append("db_url_safety.fail_if_allowed_and_forbidden_both_present must be true")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_safe_namespace(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    namespace = data.get("safe_namespace") or {}
    blockers: list[str] = []
    for field in ("template_code_prefix", "operator", "idempotency_key_prefix"):
        if not namespace.get(field):
            blockers.append(f"safe_namespace.{field} must be non-empty")
    if namespace.get("delete_required") is not False:
        blockers.append("safe_namespace.delete_required must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_smoke_matrix(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    matrix = data.get("smoke_matrix") or {}
    read_cases = {str(item) for item in _as_list(matrix.get("read"))}
    write_cases = {str(item) for item in _as_list(matrix.get("write"))}
    blockers: list[str] = []
    missing_read = sorted(READ_CASES - read_cases)
    missing_write = sorted(WRITE_CASES - write_cases)
    if missing_read:
        blockers.append(f"smoke read cases missing {missing_read}")
    if missing_write:
        blockers.append(f"smoke write cases missing {missing_write}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_side_effect_safety(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    safety = data.get("side_effect_safety") or {}
    blockers = [f"side_effect_safety.{field} must be false" for field in sorted(SIDE_EFFECT_FALSE_FIELDS) if safety.get(field) is not False]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4n_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    rec = data.get("phase_4n_recommendation") or {}
    blockers: list[str] = []
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4n_recommendation.recommended_next_step missing")
    for field in (
        "staging_smoke_execution_allowed_without_owner_approval",
        "production_dry_run_allowed",
        "production_route_switch_allowed",
    ):
        if rec.get(field) is not False:
            blockers.append(f"phase_4n_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_runner_source() -> dict[str, Any]:
    source = _read(RUNNER)
    blockers: list[str] = []
    required_markers = [
        "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND",
        "ALLOWED_DB_MARKERS",
        "FORBIDDEN_DB_MARKERS",
        "--execute-writes",
        "--output-json",
        "--output-md",
        "dry_run = not execute_writes",
    ]
    for marker in required_markers:
        if marker not in source:
            blockers.append(f"runner missing marker: {marker}")
    forbidden_fallbacks = [
        'os.environ.get("DATABASE_URL"',
        "os.getenv(\"DATABASE_URL\"",
        "get_settings(",
    ]
    for marker in forbidden_fallbacks:
        if marker in source:
            blockers.append(f"runner must not use production DB fallback: {marker}")
    lowered = source.lower()
    for pattern in FORBIDDEN_RUNNER_PATTERNS:
        if re.search(pattern, lowered):
            blockers.append(f"runner includes forbidden import/call marker: {pattern}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4M staging smoke package scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_doc_claims() -> dict[str, Any]:
    text = _read(DOC).lower()
    blockers: list[str] = []
    forbidden_phrases = [
        "staging smoke executed",
        "production dry-run authorized",
        "production repository enabled",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ]
    for phrase in forbidden_phrases:
        if phrase in text:
            blockers.append(f"doc appears to claim forbidden state: {phrase}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def build_report() -> dict[str, Any]:
    data = load_yaml()
    checks = {
        "required_docs": check_required_docs(),
        "top_level": check_top_level(data),
        "runner_config": check_runner_config(data),
        "db_url_safety": check_db_url_safety(data),
        "safe_namespace": check_safe_namespace(data),
        "smoke_matrix": check_smoke_matrix(data),
        "side_effect_safety": check_side_effect_safety(data),
        "phase4n_recommendation": check_phase4n_recommendation(data),
        "runner_source": check_runner_source(),
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
        "# Phase 4M Profile Segment Template Staging Smoke Package Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4M profile segment template staging smoke package.")
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
