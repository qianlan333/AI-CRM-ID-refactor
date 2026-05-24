#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4y_profile_segment_template_production_readonly_preflight.md"
PLAN_YAML = ROOT / "docs/development/phase_4y_profile_segment_template_production_readonly_preflight.yaml"
TOOL = ROOT / "tools/run_phase4y_profile_segment_template_production_readonly_preflight.py"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    TOOL,
    ROOT / "docs/development/phase_4x_profile_segment_template_production_readonly_final_gate.md",
    ROOT / "docs/development/phase_4w_profile_segment_template_production_readonly_execution_ready_gate.md",
]
AUTH_FALSE_FIELDS = {
    "production_dry_run_execution_authorized",
    "production_data_connection_authorized",
    "production_write_authorized",
    "production_repository_route_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "production_write_canary_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
CLOSURE_ITEMS = {
    "automation_engine_owner_approval",
    "integration_gateway_owner_approval",
    "db_config_owner_approval",
    "business_owner_approval",
    "rollback_owner_assigned",
    "dry_run_operator_assigned",
    "release_config_reviewer_approval",
    "security_data_reviewer_approval",
    "production_config_review_completed",
    "production_db_env_confirmed",
    "read_only_flags_confirmed",
    "evidence_path_confirmed",
    "fallback_validation_plan_confirmed",
    "secret_redaction_confirmed",
    "pii_redaction_confirmed",
}
ALLOWED_CLOSURE_STATUSES = {"pending", "completed", "blocked", "not_applicable"}
PREFLIGHT_TRUE_FIELDS = {
    "phase_4x_yaml_required",
    "optional_closure_status_file_supported",
    "env_flag_check_supported",
    "cli_arg_check_supported",
    "db_connection_forbidden",
    "dry_run_execution_forbidden",
}
PHASE_4Z_CONSTRAINTS = {
    "read_only_only",
    "create_update_delete_forbidden",
    "production_write_forbidden",
    "route_switch_forbidden",
    "fallback_removal_forbidden",
    "production_compat_change_forbidden",
    "external_calls_forbidden",
    "raw_pii_export_forbidden",
    "secret_export_forbidden",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4y_profile_segment_template_production_readonly_preflight.md",
    "docs/development/phase_4y_profile_segment_template_production_readonly_preflight.yaml",
    "tools/run_phase4y_profile_segment_template_production_readonly_preflight.py",
    "tools/check_phase4y_profile_segment_template_production_readonly_preflight.py",
    "tests/test_phase4y_profile_segment_template_production_readonly_preflight.py",
    "tools/check_phase4x_profile_segment_template_production_readonly_final_gate.py",
    "tools/check_phase4w_profile_segment_template_production_readonly_execution_ready_gate.py",
    "tools/check_phase4v_profile_segment_template_production_readonly_execution_blocker_and_readiness.py",
    "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.md",
    "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.yaml",
    "tools/check_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
    "tests/test_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
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
    "production data connected",
    "production write executed",
    "production repository enabled as route owner",
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
    if data.get("status") != "phase_4y_production_readonly_preflight_no_execution":
        blockers.append("status must be phase_4y_production_readonly_preflight_no_execution")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_closure_items(data: dict[str, Any] | None = None) -> dict[str, Any]:
    closure = (data or load_yaml()).get("closure_items") or {}
    blockers: list[str] = []
    missing = sorted(CLOSURE_ITEMS - set(closure))
    if missing:
        blockers.append(f"closure_items missing {missing}")
    for field in sorted(CLOSURE_ITEMS):
        if closure.get(field) not in ALLOWED_CLOSURE_STATUSES:
            blockers.append(f"closure_items.{field} must be one of {sorted(ALLOWED_CLOSURE_STATUSES)}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_preflight_inputs(data: dict[str, Any] | None = None) -> dict[str, Any]:
    preflight = (data or load_yaml()).get("preflight_inputs") or {}
    blockers = [
        f"preflight_inputs.{field} must be true"
        for field in sorted(PREFLIGHT_TRUE_FIELDS)
        if preflight.get(field) is not True
    ]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_readiness(data: dict[str, Any] | None = None) -> dict[str, Any]:
    readiness = (data or load_yaml()).get("readiness") or {}
    blockers: list[str] = []
    if readiness.get("ready_for_phase_4z_readonly_dry_run_execution") is not False:
        blockers.append("readiness.ready_for_phase_4z_readonly_dry_run_execution must default to false")
    for field in (
        "missing_items",
        "blockers",
        "next_owner_actions",
        "next_config_actions",
        "next_evidence_actions",
    ):
        if not _as_list(readiness.get(field)):
            blockers.append(f"readiness.{field} must be non-empty")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase_4z_constraints(data: dict[str, Any] | None = None) -> dict[str, Any]:
    constraints = (data or load_yaml()).get("phase_4z_constraints") or {}
    blockers = [
        f"phase_4z_constraints.{field} must be true"
        for field in sorted(PHASE_4Z_CONSTRAINTS)
        if constraints.get(field) is not True
    ]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase_4z_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = (data or load_yaml()).get("phase_4z_recommendation") or {}
    blockers: list[str] = []
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4z_recommendation.recommended_next_step missing")
    for field in (
        "production_write_allowed",
        "production_route_switch_allowed",
        "fallback_removal_allowed",
        "production_write_canary_allowed",
    ):
        if rec.get(field) is not False:
            blockers.append(f"phase_4z_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_tool_source() -> dict[str, Any]:
    source = _read(TOOL)
    blockers: list[str] = []
    forbidden_tokens = {
        "create_engine": "must not reference SQLAlchemy create_engine",
        "from sqlalchemy": "must not import DB engine",
        "import sqlalchemy": "must not import DB engine",
        "subprocess": "must not execute a dry-run subprocess",
        "run_phase4r": "must not call Phase 4R runner",
        "run_phase4u": "must not call Phase 4U runner",
    }
    for token, reason in forbidden_tokens.items():
        if token in source:
            blockers.append(reason)
    for token in (
        "--closure-status-file",
        "--read-only",
        "--confirm-no-writes",
        "--output-json",
        "--output-md",
    ):
        if token not in source:
            blockers.append(f"tool must support {token}")
    if "db_url_secret_redacted" not in source or "_redacted_db_presence" not in source:
        blockers.append("tool must redact secrets")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4Y scope: {unexpected}")
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
        "closure_items": check_closure_items(data),
        "preflight_inputs": check_preflight_inputs(data),
        "readiness": check_readiness(data),
        "phase_4z_constraints": check_phase_4z_constraints(data),
        "phase_4z_recommendation": check_phase_4z_recommendation(data),
        "tool_source": check_tool_source(),
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
        "# Phase 4Y Profile Segment Template Production Read-Only Preflight Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4Y profile segment template production read-only preflight.")
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
