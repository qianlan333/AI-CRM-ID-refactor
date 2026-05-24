#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4p_profile_segment_template_production_dry_run_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4p_profile_segment_template_production_dry_run_plan.yaml"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    ROOT / "docs/development/phase_4o_profile_segment_template_staging_smoke_evidence.md",
    ROOT / "docs/development/phase_4n_profile_segment_template_staging_smoke_approval.md",
]
AUTH_FALSE_FIELDS = {
    "production_dry_run_execution_authorized",
    "production_repository_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "production_write_canary_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
PRECONDITION_TRUE_FIELDS = {
    "staging_smoke_evidence_required",
    "owner_approval_required",
    "production_config_review_required",
    "rollback_owner_required",
    "db_config_owner_required",
    "fallback_validation_required",
    "production_compat_retained_required",
}
READ_ONLY_SCOPE = {"catalog", "list", "options", "detail"}
WRITE_SHADOW_SCOPE = {
    "create_validation_only",
    "update_validation_only",
    "idempotency_conflict_simulation",
    "rollback_payload_generation",
}
FORBIDDEN_SCOPE = {
    "route_owner_switch",
    "fallback_removal",
    "production_write_canary",
    "external_call",
    "workflow_activation",
    "automation_execution",
    "customer_pool_state_change",
}
DATA_SAFETY_TRUE_FIELDS = {
    "secret_redaction_required",
    "pii_redaction_required",
    "raw_payload_export_forbidden",
    "safe_namespace_required_for_future_writes",
    "delete_requires_separate_approval",
}
EVIDENCE_REQUIRED = {
    "command",
    "config_summary_without_secrets",
    "route_owner_unchanged_evidence",
    "production_compat_retained_evidence",
    "read_parity_summary",
    "validation_shadow_summary",
    "failed_skipped_details",
    "side_effect_safety_summary",
    "fallback_validation",
    "operator_timestamp",
    "owner_signoff",
}
STOP_CONDITIONS = {
    "production_config_review_incomplete",
    "owner_approval_missing",
    "fallback_validation_failed",
    "side_effect_safety_failed",
    "external_call_detected",
    "route_owner_changed",
    "production_compat_changed",
    "unexpected_write_attempted",
    "secret_redaction_failed",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4p_profile_segment_template_production_dry_run_plan.md",
    "docs/development/phase_4p_profile_segment_template_production_dry_run_plan.yaml",
    "tools/check_phase4p_profile_segment_template_production_dry_run_plan.py",
    "tests/test_phase4p_profile_segment_template_production_dry_run_plan.py",
    "tools/check_phase4o_profile_segment_template_staging_smoke_evidence.py",
    "tools/check_phase4n_profile_segment_template_staging_smoke_approval.py",
    "docs/development/phase_4q_profile_segment_template_production_dry_run_approval.md",
    "docs/development/phase_4q_profile_segment_template_production_dry_run_approval.yaml",
    "tools/check_phase4q_profile_segment_template_production_dry_run_approval.py",
    "tests/test_phase4q_profile_segment_template_production_dry_run_approval.py",
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
    "production dry-run executed",
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
    if data.get("status") != "phase_4p_production_dry_run_planning_only_no_execution":
        blockers.append("status must be phase_4p_production_dry_run_planning_only_no_execution")
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


def check_preconditions(data: dict[str, Any] | None = None) -> dict[str, Any]:
    preconditions = (data or load_yaml()).get("preconditions") or {}
    blockers = [f"preconditions.{field} must be true" for field in sorted(PRECONDITION_TRUE_FIELDS) if preconditions.get(field) is not True]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_dry_run_levels(data: dict[str, Any] | None = None) -> dict[str, Any]:
    levels = _as_list((data or load_yaml()).get("dry_run_levels"))
    by_level = {item.get("level"): item for item in levels if isinstance(item, dict)}
    blockers: list[str] = []
    if set(by_level) != {0, 1, 2, 3, 4}:
        blockers.append("dry_run_levels must include levels 0-4")
    for level, item in sorted(by_level.items()):
        expected = level == 0
        if item.get("authorized_now") is not expected:
            blockers.append(f"dry_run_levels level {level} authorized_now must be {expected}")
    if by_level.get(4, {}).get("authorized_now") is not False:
        blockers.append("level 4 must not be authorized")
    if by_level.get(0, {}).get("production_data_access_allowed") is not False:
        blockers.append("level 0 production_data_access_allowed must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_future_scope(data: dict[str, Any] | None = None) -> dict[str, Any]:
    scope = (data or load_yaml()).get("future_scope") or {}
    blockers: list[str] = []
    read_only = {str(item) for item in _as_list(scope.get("read_only"))}
    write_shadow = {str(item) for item in _as_list(scope.get("write_shadow"))}
    forbidden = {str(item) for item in _as_list(scope.get("forbidden"))}
    missing_read = sorted(READ_ONLY_SCOPE - read_only)
    missing_write = sorted(WRITE_SHADOW_SCOPE - write_shadow)
    missing_forbidden = sorted(FORBIDDEN_SCOPE - forbidden)
    if missing_read:
        blockers.append(f"future_scope.read_only missing {missing_read}")
    if missing_write:
        blockers.append(f"future_scope.write_shadow missing {missing_write}")
    if missing_forbidden:
        blockers.append(f"future_scope.forbidden missing {missing_forbidden}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_data_safety(data: dict[str, Any] | None = None) -> dict[str, Any]:
    safety = (data or load_yaml()).get("data_safety") or {}
    blockers = [f"data_safety.{field} must be true" for field in sorted(DATA_SAFETY_TRUE_FIELDS) if safety.get(field) is not True]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_evidence_package(data: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = (data or load_yaml()).get("evidence_package") or {}
    present = {str(item) for item in _as_list(evidence.get("required"))}
    missing = sorted(EVIDENCE_REQUIRED - present)
    blockers = [f"evidence_package.required missing {missing}"] if missing else []
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_stop_conditions(data: dict[str, Any] | None = None) -> dict[str, Any]:
    present = {str(item) for item in _as_list((data or load_yaml()).get("stop_conditions"))}
    missing = sorted(STOP_CONDITIONS - present)
    blockers = [f"stop_conditions missing {missing}"] if missing else []
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4q_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = (data or load_yaml()).get("phase_4q_recommendation") or {}
    blockers: list[str] = []
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4q_recommendation.recommended_next_step missing")
    for field in (
        "production_dry_run_execution_allowed_without_owner_approval",
        "production_route_switch_allowed",
        "production_write_canary_allowed",
    ):
        if rec.get(field) is not False:
            blockers.append(f"phase_4q_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4P production dry-run plan scope: {unexpected}")
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
        "preconditions": check_preconditions(data),
        "dry_run_levels": check_dry_run_levels(data),
        "future_scope": check_future_scope(data),
        "data_safety": check_data_safety(data),
        "evidence_package": check_evidence_package(data),
        "stop_conditions": check_stop_conditions(data),
        "phase4q_recommendation": check_phase4q_recommendation(data),
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
        "# Phase 4P Profile Segment Template Production Dry-Run Plan Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4P profile segment template production dry-run plan.")
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
