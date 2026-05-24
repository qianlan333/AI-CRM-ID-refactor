#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4t_profile_segment_template_readonly_dry_run_review.md"
PLAN_YAML = ROOT / "docs/development/phase_4t_profile_segment_template_readonly_dry_run_review.yaml"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    ROOT / "docs/development/phase_4s_profile_segment_template_production_readonly_dry_run_evidence.md",
    ROOT / "docs/development/phase_4s_profile_segment_template_production_readonly_dry_run_evidence.yaml",
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
EVIDENCE_REVIEW_FIELDS = {
    "result_status",
    "phase_4s_evidence_present",
    "production_readonly_dry_run_executed",
    "blocked_evidence_only",
    "approval_present",
    "config_reviewed",
    "read_parity_summary_present",
    "side_effect_safety_passed",
    "writes_attempted",
    "route_owner_changed",
    "production_compat_changed",
    "fallback_retained",
    "blockers",
}
RESULT_STATUSES = {
    "blocked_only_no_production_dry_run_executed",
    "read_only_dry_run_executed_and_passed",
    "read_only_dry_run_executed_with_blockers",
    "evidence_missing_or_incomplete",
}
REQUIRED_BEFORE_READY = {
    "actual_production_readonly_dry_run_executed",
    "read_parity_passed",
    "no_writes_attempted",
    "side_effect_safety_false",
    "fallback_validation_passed",
    "production_compat_unchanged",
    "owner_approval_completed",
    "rollback_owner_assigned",
    "production_config_review_completed",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4t_profile_segment_template_readonly_dry_run_review.md",
    "docs/development/phase_4t_profile_segment_template_readonly_dry_run_review.yaml",
    "tools/check_phase4t_profile_segment_template_readonly_dry_run_review.py",
    "tests/test_phase4t_profile_segment_template_readonly_dry_run_review.py",
    "tools/check_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py",
    "tools/check_phase4r_profile_segment_template_production_readonly_dry_run_runner.py",
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
    if data.get("status") != "phase_4t_readonly_dry_run_review_no_route_switch":
        blockers.append("status must be phase_4t_readonly_dry_run_review_no_route_switch")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_evidence_review(data: dict[str, Any] | None = None) -> dict[str, Any]:
    review = (data or load_yaml()).get("evidence_review") or {}
    blockers: list[str] = []
    missing = sorted(field for field in EVIDENCE_REVIEW_FIELDS if field not in review)
    if missing:
        blockers.append(f"evidence_review missing {missing}")
    if review.get("result_status") not in RESULT_STATUSES:
        blockers.append("evidence_review.result_status must be an allowed value")
    for field in ("writes_attempted", "route_owner_changed", "production_compat_changed"):
        if review.get(field) is not False:
            blockers.append(f"evidence_review.{field} must be false")
    if review.get("fallback_retained") is not True:
        blockers.append("evidence_review.fallback_retained must be true")
    if not _as_list(review.get("blockers")):
        blockers.append("evidence_review.blockers must be non-empty")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_route_switch_readiness(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    review = data.get("evidence_review") or {}
    readiness = data.get("route_switch_readiness") or {}
    blockers: list[str] = []
    if review.get("production_readonly_dry_run_executed") is False and readiness.get("ready") is not False:
        blockers.append("route_switch_readiness.ready must be false when production read-only dry-run has not executed")
    present = {str(item) for item in _as_list(readiness.get("required_before_ready"))}
    missing = sorted(REQUIRED_BEFORE_READY - present)
    if missing:
        blockers.append(f"route_switch_readiness.required_before_ready missing {missing}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4u_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    review = data.get("evidence_review") or {}
    rec = data.get("phase_4u_recommendation") or {}
    blockers: list[str] = []
    next_step = str(rec.get("recommended_next_step") or "")
    if not next_step:
        blockers.append("phase_4u_recommendation.recommended_next_step missing")
    if review.get("production_readonly_dry_run_executed") is False:
        normalized = next_step.replace("_", " ").replace("-", " ").lower()
        if not all(token in normalized for token in ("read", "dry", "run", "execution", "evidence")):
            blockers.append("phase_4u_recommendation.recommended_next_step must point to read-only dry-run execution evidence when execution is missing")
    for field in (
        "production_write_allowed",
        "production_route_switch_allowed",
        "fallback_removal_allowed",
        "production_write_canary_allowed",
    ):
        if rec.get(field) is not False:
            blockers.append(f"phase_4u_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4T readonly dry-run review scope: {unexpected}")
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
        "evidence_review": check_evidence_review(data),
        "route_switch_readiness": check_route_switch_readiness(data),
        "phase4u_recommendation": check_phase4u_recommendation(data),
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
        "# Phase 4T Profile Segment Template Read-Only Dry-Run Review Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4T profile segment template read-only dry-run review.")
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
