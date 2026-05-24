#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4n_profile_segment_template_staging_smoke_approval.md"
PLAN_YAML = ROOT / "docs/development/phase_4n_profile_segment_template_staging_smoke_approval.yaml"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    ROOT / "docs/development/phase_4m_profile_segment_template_staging_smoke_package.md",
    ROOT / "docs/development/phase_4l_profile_segment_template_staging_smoke_plan.md",
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
APPROVAL_FIELDS = {
    "automation_engine_owner",
    "integration_gateway_owner",
    "db_config_owner",
    "business_owner",
    "rollback_owner",
    "smoke_operator",
    "release_config_reviewer",
}
ALLOWED_DB_MARKERS = {"staging", "stage", "test", "local", "dev"}
FORBIDDEN_DB_MARKERS = {"prod", "production", "primary", "master"}
REQUIRED_FEATURE_FLAGS = {
    "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND",
    "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL",
}
EXECUTION_TRUE_FIELDS = {
    "manual_execution_required",
    "dry_run_first_required",
    "execute_writes_requires_owner_approval",
    "evidence_required",
}
STOP_CONDITIONS = {
    "db_url_safety_failed",
    "smoke_write_failed",
    "unexpected_idempotency_conflict",
    "audit_row_missing",
    "rollback_payload_missing",
    "side_effect_safety_failed",
    "external_call_detected",
    "production_marker_detected",
    "fallback_validation_failed",
}
ROLLBACK_TRUE_FIELDS = {
    "feature_flag_disable_required",
    "safe_namespace_cleanup_required",
    "audit_review_required",
    "evidence_preservation_required",
    "delete_requires_separate_approval",
    "fallback_validation_required",
}
EVIDENCE_REQUIRED = {
    "runner_json_report",
    "runner_markdown_report",
    "db_url_safety_summary_without_secret",
    "smoke_matrix_summary",
    "failed_skipped_details",
    "audit_rollback_evidence",
    "side_effect_safety_summary",
    "operator_timestamp",
    "owner_signoff",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4n_profile_segment_template_staging_smoke_approval.md",
    "docs/development/phase_4n_profile_segment_template_staging_smoke_approval.yaml",
    "tools/check_phase4n_profile_segment_template_staging_smoke_approval.py",
    "tests/test_phase4n_profile_segment_template_staging_smoke_approval.py",
    "tools/check_phase4m_profile_segment_template_staging_smoke_package.py",
    "tools/check_phase4l_profile_segment_template_staging_smoke_plan.py",
    "tools/check_phase4k_profile_segment_template_local_parity_harness.py",
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
    "staging smoke executed",
    "production dry-run authorized",
    "production repository enabled",
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
    if data.get("status") != "phase_4n_staging_smoke_approval_only_no_execution":
        blockers.append("status must be phase_4n_staging_smoke_approval_only_no_execution")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_approval(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    approval = data.get("approval") or {}
    blockers = [f"approval.{field} must be pending" for field in sorted(APPROVAL_FIELDS) if approval.get(field) != "pending"]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_environment_confirmation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    env = data.get("environment_confirmation") or {}
    blockers: list[str] = []
    if env.get("staging_db_url_required") is not True:
        blockers.append("environment_confirmation.staging_db_url_required must be true")
    if not ALLOWED_DB_MARKERS <= {str(item) for item in _as_list(env.get("allowed_db_url_markers"))}:
        blockers.append("environment_confirmation.allowed_db_url_markers missing required markers")
    if not FORBIDDEN_DB_MARKERS <= {str(item) for item in _as_list(env.get("forbidden_db_url_markers"))}:
        blockers.append("environment_confirmation.forbidden_db_url_markers missing required markers")
    if not REQUIRED_FEATURE_FLAGS <= {str(item) for item in _as_list(env.get("required_feature_flags"))}:
        blockers.append("environment_confirmation.required_feature_flags missing required flags")
    if env.get("database_url_fallback_allowed") is not False:
        blockers.append("environment_confirmation.database_url_fallback_allowed must be false")
    if env.get("production_data_allowed") is not False:
        blockers.append("environment_confirmation.production_data_allowed must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_execution_plan(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    plan = data.get("execution_plan") or {}
    blockers: list[str] = []
    for field in sorted(EXECUTION_TRUE_FIELDS):
        if plan.get(field) is not True:
            blockers.append(f"execution_plan.{field} must be true")
    if plan.get("run_in_ci_by_default") is not False:
        blockers.append("execution_plan.run_in_ci_by_default must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_stop_conditions(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    present = {str(item) for item in _as_list(data.get("stop_conditions"))}
    missing = sorted(STOP_CONDITIONS - present)
    blockers = [f"stop_conditions missing {missing}"] if missing else []
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_rollback_plan(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    plan = data.get("rollback_plan") or {}
    blockers = [f"rollback_plan.{field} must be true" for field in sorted(ROLLBACK_TRUE_FIELDS) if plan.get(field) is not True]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_evidence_package(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    package = data.get("evidence_package") or {}
    present = {str(item) for item in _as_list(package.get("required"))}
    missing = sorted(EVIDENCE_REQUIRED - present)
    blockers = [f"evidence_package.required missing {missing}"] if missing else []
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4o_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    rec = data.get("phase_4o_recommendation") or {}
    blockers: list[str] = []
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4o_recommendation.recommended_next_step missing")
    for field in (
        "staging_smoke_execution_allowed_without_owner_approval",
        "production_dry_run_allowed",
        "production_route_switch_allowed",
        "production_write_canary_allowed",
    ):
        if rec.get(field) is not False:
            blockers.append(f"phase_4o_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4N staging smoke approval scope: {unexpected}")
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
        "top_level": check_top_level(data),
        "approval": check_approval(data),
        "environment_confirmation": check_environment_confirmation(data),
        "execution_plan": check_execution_plan(data),
        "stop_conditions": check_stop_conditions(data),
        "rollback_plan": check_rollback_plan(data),
        "evidence_package": check_evidence_package(data),
        "phase4o_recommendation": check_phase4o_recommendation(data),
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
        "# Phase 4N Profile Segment Template Staging Smoke Approval Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4N profile segment template staging smoke approval package.")
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
