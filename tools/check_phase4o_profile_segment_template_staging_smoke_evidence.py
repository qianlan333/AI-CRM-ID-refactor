#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4o_profile_segment_template_staging_smoke_evidence.md"
PLAN_YAML = ROOT / "docs/development/phase_4o_profile_segment_template_staging_smoke_evidence.yaml"
RUNNER = ROOT / "tools/run_phase4o_profile_segment_template_staging_smoke_evidence.py"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    RUNNER,
    ROOT / "docs/development/phase_4n_profile_segment_template_staging_smoke_approval.md",
    ROOT / "docs/development/phase_4m_profile_segment_template_staging_smoke_package.md",
]
AUTH_FALSE_FIELDS = {
    "production_data_used",
    "production_repository_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "production_dry_run_authorized",
    "production_write_canary_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
EXECUTION_FIELDS = {
    "result_status",
    "dry_run_attempted",
    "dry_run_passed",
    "write_smoke_attempted",
    "write_smoke_passed",
    "write_smoke_owner_approved",
    "not_executed_reason",
}
DB_SAFETY_FIELDS = {
    "checked",
    "safe",
    "allowed_marker_present",
    "forbidden_marker_present",
    "secret_redacted",
    "production_data_used",
}
SIDE_EFFECT_FALSE_FIELDS = {
    "external_calls_executed",
    "automation_execution_executed",
    "outbound_send_executed",
    "route_owner_changed",
    "production_compat_changed",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4o_profile_segment_template_staging_smoke_evidence.md",
    "docs/development/phase_4o_profile_segment_template_staging_smoke_evidence.yaml",
    "tools/run_phase4o_profile_segment_template_staging_smoke_evidence.py",
    "tools/check_phase4o_profile_segment_template_staging_smoke_evidence.py",
    "tests/test_phase4o_profile_segment_template_staging_smoke_evidence.py",
    "tools/check_phase4m_profile_segment_template_staging_smoke_package.py",
    "tools/check_phase4n_profile_segment_template_staging_smoke_approval.py",
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
    "production dry-run authorized",
    "production repository enabled",
    "route switch authorized",
    "fallback removal authorized",
    "production approved",
    "canary approved",
    "delete_ready true",
]
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
    r"\bimport\s+.*timer",
    r"\bfrom\s+.*timer",
    r"\bimport\s+.*send",
    r"\bfrom\s+.*send",
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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def check_required_docs() -> dict[str, Any]:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_DOCS if not path.exists()]
    return {"ok": not missing, "blockers": [f"missing required file: {path}" for path in missing], "warnings": []}


def check_top_level(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if data.get("status") != "phase_4o_staging_smoke_evidence_no_production_change":
        blockers.append("status must be phase_4o_staging_smoke_evidence_no_production_change")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_execution(data: dict[str, Any] | None = None) -> dict[str, Any]:
    execution = (data or load_yaml()).get("execution") or {}
    missing = sorted(field for field in EXECUTION_FIELDS if field not in execution)
    blockers = [f"execution missing fields {missing}"] if missing else []
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_db_url_safety(data: dict[str, Any] | None = None) -> dict[str, Any]:
    safety = (data or load_yaml()).get("db_url_safety") or {}
    missing = sorted(field for field in DB_SAFETY_FIELDS if field not in safety)
    blockers = [f"db_url_safety missing fields {missing}"] if missing else []
    if safety.get("checked") is not True:
        blockers.append("db_url_safety.checked must be true")
    if safety.get("secret_redacted") is not True:
        blockers.append("db_url_safety.secret_redacted must be true")
    if safety.get("production_data_used") is not False:
        blockers.append("db_url_safety.production_data_used must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_side_effect_safety(data: dict[str, Any] | None = None) -> dict[str, Any]:
    safety = (data or load_yaml()).get("side_effect_safety") or {}
    blockers = [f"side_effect_safety.{field} must be false" for field in sorted(SIDE_EFFECT_FALSE_FIELDS) if safety.get(field) is not False]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4p_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = (data or load_yaml()).get("phase_4p_recommendation") or {}
    blockers: list[str] = []
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4p_recommendation.recommended_next_step missing")
    for field in ("production_dry_run_allowed", "production_route_switch_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4p_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_runner_source() -> dict[str, Any]:
    source = _read(RUNNER)
    blockers: list[str] = []
    required_markers = [
        "AICRM_PHASE4O_STAGING_WRITE_APPROVED",
        "--execute-writes",
        "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL",
        "FORBIDDEN_DB_MARKERS",
        "--output-json",
        "--output-md",
        "_redact_url",
        "not_executed_missing_staging_db",
        "not_executed_db_url_safety_failed",
        "not_executed_missing_approval",
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
            blockers.append(f"runner includes forbidden external side-effect marker: {pattern}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4O staging smoke evidence scope: {unexpected}")
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
        "db_url_safety": check_db_url_safety(data),
        "side_effect_safety": check_side_effect_safety(data),
        "phase4p_recommendation": check_phase4p_recommendation(data),
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
        "# Phase 4O Profile Segment Template Staging Smoke Evidence Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4O profile segment template staging smoke evidence package.")
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
