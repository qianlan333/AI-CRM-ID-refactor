#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4s_profile_segment_template_production_readonly_dry_run_evidence.md"
PLAN_YAML = ROOT / "docs/development/phase_4s_profile_segment_template_production_readonly_dry_run_evidence.yaml"
TOOL = ROOT / "tools/run_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    TOOL,
    ROOT / "docs/development/phase_4r_profile_segment_template_production_readonly_dry_run_runner.md",
    ROOT / "docs/development/phase_4q_profile_segment_template_production_dry_run_approval.md",
]
AUTH_FALSE_FIELDS = {
    "production_write_authorized",
    "production_repository_route_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "production_write_canary_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
EXECUTION_FIELDS = {
    "result_status",
    "read_only_dry_run_attempted",
    "read_only_dry_run_executed",
    "approval_present",
    "config_reviewed",
    "production_db_present",
    "read_only_flags_present",
    "not_executed_reason",
    "writes_attempted",
}
EVIDENCE_FALSE_FIELDS = {"route_owner_changed", "production_compat_changed"}
SIDE_EFFECT_FALSE_FIELDS = {
    "external_calls_executed",
    "automation_execution_executed",
    "outbound_send_executed",
    "create_update_delete_executed",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4s_profile_segment_template_production_readonly_dry_run_evidence.md",
    "docs/development/phase_4s_profile_segment_template_production_readonly_dry_run_evidence.yaml",
    "tools/run_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py",
    "tools/check_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py",
    "tests/test_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py",
    "tools/check_phase4r_profile_segment_template_production_readonly_dry_run_runner.py",
    "docs/development/phase_4t_profile_segment_template_readonly_dry_run_review.md",
    "docs/development/phase_4t_profile_segment_template_readonly_dry_run_review.yaml",
    "tools/check_phase4t_profile_segment_template_readonly_dry_run_review.py",
    "tests/test_phase4t_profile_segment_template_readonly_dry_run_review.py",
    "docs/development/phase_4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.md",
    "docs/development/phase_4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.yaml",
    "tools/run_phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.py",
    "tools/check_phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.py",
    "tests/test_phase4u_profile_segment_template_production_readonly_dry_run_evidence_and_review.py",
    "docs/development/phase_4u_profile_segment_template_production_readonly_dry_run_execution_evidence.md",
    "docs/development/phase_4u_profile_segment_template_production_readonly_dry_run_execution_evidence.yaml",
    "tools/run_phase4u_profile_segment_template_production_readonly_dry_run_execution_evidence.py",
    "tools/check_phase4u_profile_segment_template_production_readonly_dry_run_execution_evidence.py",
    "tests/test_phase4u_profile_segment_template_production_readonly_dry_run_execution_evidence.py",
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
    if data.get("status") != "phase_4s_production_readonly_dry_run_evidence_no_route_switch":
        blockers.append("status must be phase_4s_production_readonly_dry_run_evidence_no_route_switch")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_execution(data: dict[str, Any] | None = None) -> dict[str, Any]:
    execution = (data or load_yaml()).get("execution") or {}
    blockers: list[str] = []
    missing = sorted(field for field in EXECUTION_FIELDS if field not in execution)
    if missing:
        blockers.append(f"execution missing {missing}")
    if execution.get("writes_attempted") is not False:
        blockers.append("execution.writes_attempted must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_evidence(data: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = (data or load_yaml()).get("evidence") or {}
    blockers: list[str] = []
    if evidence.get("db_url_secret_redacted") is not True:
        blockers.append("evidence.db_url_secret_redacted must be true")
    if evidence.get("fallback_retained") is not True:
        blockers.append("evidence.fallback_retained must be true")
    if evidence.get("side_effect_safety_present") is not True:
        blockers.append("evidence.side_effect_safety_present must be true")
    for field in sorted(EVIDENCE_FALSE_FIELDS):
        if evidence.get(field) is not False:
            blockers.append(f"evidence.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_side_effect_safety(data: dict[str, Any] | None = None) -> dict[str, Any]:
    safety = (data or load_yaml()).get("side_effect_safety") or {}
    blockers = [
        f"side_effect_safety.{field} must be false"
        for field in sorted(SIDE_EFFECT_FALSE_FIELDS)
        if safety.get(field) is not False
    ]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4t_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = (data or load_yaml()).get("phase_4t_recommendation") or {}
    blockers: list[str] = []
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4t_recommendation.recommended_next_step missing")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4t_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _uses_forbidden_env_fallback(source: str) -> bool:
    return bool(
        re.search(r"os\.environ\.get\(\s*[\"']DATABASE_URL[\"']", source)
        or re.search(r"os\.getenv\(\s*[\"']DATABASE_URL[\"']", source)
    )


def check_tool_source() -> dict[str, Any]:
    source = _read(TOOL)
    blockers: list[str] = []
    for token in (
        "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED",
        "AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL",
        "--read-only",
        "--confirm-no-writes",
        "--output-json",
        "--output-md",
    ):
        if token not in source:
            blockers.append(f"evidence tool must reference {token}")
    if _uses_forbidden_env_fallback(source):
        blockers.append("evidence tool must not fallback to DATABASE_URL")
    for forbidden_call in (
        ".create_profile_segment_template(",
        ".update_profile_segment_template(",
        ".delete_profile_segment_template(",
    ):
        if forbidden_call in source:
            blockers.append(f"evidence tool must not call {forbidden_call}")
    if "_redact_url" not in source or "db_url_redacted" not in source:
        blockers.append("evidence tool must redact secrets")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4S production read-only dry-run evidence scope: {unexpected}")
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
        "execution": check_execution(data),
        "evidence": check_evidence(data),
        "side_effect_safety": check_side_effect_safety(data),
        "phase4t_recommendation": check_phase4t_recommendation(data),
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
        "# Phase 4S Profile Segment Template Production Read-Only Dry-Run Evidence Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4S profile segment template production read-only dry-run evidence.")
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
