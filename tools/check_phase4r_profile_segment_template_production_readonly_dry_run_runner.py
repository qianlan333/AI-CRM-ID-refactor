#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4r_profile_segment_template_production_readonly_dry_run_runner.md"
PLAN_YAML = ROOT / "docs/development/phase_4r_profile_segment_template_production_readonly_dry_run_runner.yaml"
RUNNER = ROOT / "tools/run_phase4r_profile_segment_template_production_readonly_dry_run.py"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    RUNNER,
    ROOT / "docs/development/phase_4q_profile_segment_template_production_dry_run_approval.md",
    ROOT / "docs/development/phase_4p_profile_segment_template_production_dry_run_plan.md",
]
AUTH_FALSE_FIELDS = {
    "production_dry_run_execution_authorized",
    "production_repository_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "production_write_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
APPROVAL_ENVS = {
    "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED",
    "AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED",
}
REQUIRED_DB_ENVS = {"AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"}
REQUIRED_ARGS = {"--read-only", "--confirm-no-writes"}
FORBIDDEN_ENV_FALLBACKS = {
    "DATABASE_URL",
    "AICRM_NEXT_TEST_DATABASE_URL",
    "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL",
}
ALLOWED_OPERATIONS = {"catalog_read", "list_read", "options_read", "detail_read"}
FORBIDDEN_OPERATIONS = {
    "create",
    "update",
    "delete",
    "migration",
    "backfill",
    "idempotency_write",
    "audit_write",
    "external_call",
    "automation_execution",
    "outbound_send",
}
EVIDENCE_TRUE_FIELDS = {
    "secret_redaction_required",
    "pii_redaction_required",
    "fallback_must_remain",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4r_profile_segment_template_production_readonly_dry_run_runner.md",
    "docs/development/phase_4r_profile_segment_template_production_readonly_dry_run_runner.yaml",
    "tools/run_phase4r_profile_segment_template_production_readonly_dry_run.py",
    "tools/check_phase4r_profile_segment_template_production_readonly_dry_run_runner.py",
    "tests/test_phase4r_profile_segment_template_production_readonly_dry_run_runner.py",
    "tools/check_phase4q_profile_segment_template_production_dry_run_approval.py",
    "tools/check_phase4p_profile_segment_template_production_dry_run_plan.py",
    "docs/development/phase_4s_profile_segment_template_production_readonly_dry_run_evidence.md",
    "docs/development/phase_4s_profile_segment_template_production_readonly_dry_run_evidence.yaml",
    "tools/run_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py",
    "tools/check_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py",
    "tests/test_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py",
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
    "docs/development/phase_4v_profile_segment_template_production_readonly_execution_blocker_and_readiness.md",
    "docs/development/phase_4v_profile_segment_template_production_readonly_execution_blocker_and_readiness.yaml",
    "tools/run_phase4v_profile_segment_template_production_readonly_execution_blocker_and_readiness.py",
    "tools/check_phase4v_profile_segment_template_production_readonly_execution_blocker_and_readiness.py",
    "tests/test_phase4v_profile_segment_template_production_readonly_execution_blocker_and_readiness.py",
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
    "production route switch authorized",
    "production write authorized",
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
    if data.get("status") != "phase_4r_production_readonly_dry_run_runner_no_execution":
        blockers.append("status must be phase_4r_production_readonly_dry_run_runner_no_execution")
    for field in sorted(AUTH_FALSE_FIELDS):
        if data.get(field) is not False:
            blockers.append(f"{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_runner_config(data: dict[str, Any] | None = None) -> dict[str, Any]:
    runner = (data or load_yaml()).get("runner") or {}
    blockers: list[str] = []
    if runner.get("path") != "tools/run_phase4r_profile_segment_template_production_readonly_dry_run.py":
        blockers.append("runner.path mismatch")
    if runner.get("default_execution") != "blocked":
        blockers.append("runner.default_execution must be blocked")
    if set(_as_list(runner.get("required_approval_env"))) != APPROVAL_ENVS:
        blockers.append("runner.required_approval_env mismatch")
    if set(_as_list(runner.get("required_db_env"))) != REQUIRED_DB_ENVS:
        blockers.append("runner.required_db_env mismatch")
    if not REQUIRED_ARGS.issubset({str(item) for item in _as_list(runner.get("required_args"))}):
        blockers.append("runner.required_args must include --read-only and --confirm-no-writes")
    if not FORBIDDEN_ENV_FALLBACKS.issubset({str(item) for item in _as_list(runner.get("forbidden_env_fallbacks"))}):
        blockers.append("runner.forbidden_env_fallbacks missing required entries")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_operations(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    allowed = {str(item) for item in _as_list(data.get("allowed_operations"))}
    forbidden = {str(item) for item in _as_list(data.get("forbidden_operations"))}
    blockers: list[str] = []
    if allowed != ALLOWED_OPERATIONS:
        blockers.append("allowed_operations must contain read operations only")
    missing_forbidden = sorted(FORBIDDEN_OPERATIONS - forbidden)
    if missing_forbidden:
        blockers.append(f"forbidden_operations missing {missing_forbidden}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_evidence(data: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = (data or load_yaml()).get("evidence") or {}
    blockers: list[str] = []
    for field in sorted(EVIDENCE_TRUE_FIELDS):
        if evidence.get(field) is not True:
            blockers.append(f"evidence.{field} must be true")
    for field in ("raw_payload_export_allowed", "route_owner_changed_allowed", "production_compat_changed_allowed"):
        if evidence.get(field) is not False:
            blockers.append(f"evidence.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4s_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = (data or load_yaml()).get("phase_4s_recommendation") or {}
    blockers: list[str] = []
    if rec.get("recommended_next_step") != "production_read_only_dry_run_execution_evidence":
        blockers.append("phase_4s_recommendation.recommended_next_step mismatch")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4s_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _uses_forbidden_env_fallback(source: str, env_name: str) -> bool:
    patterns = [
        rf"os\.environ\.get\(\s*[\"']{re.escape(env_name)}[\"']",
        rf"os\.getenv\(\s*[\"']{re.escape(env_name)}[\"']",
    ]
    return any(re.search(pattern, source) for pattern in patterns)


def _executable_source_lines(source: str) -> list[str]:
    lines: list[str] = []
    for raw in source.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def check_runner_source() -> dict[str, Any]:
    source = _read(RUNNER)
    blockers: list[str] = []
    for token in APPROVAL_ENVS | REQUIRED_DB_ENVS:
        if token not in source:
            blockers.append(f"runner source must reference {token}")
    for token in REQUIRED_ARGS | {"--output-json", "--output-md"}:
        if token not in source:
            blockers.append(f"runner source must support {token}")
    if "_redact_url" not in source or "db_url_redacted" not in source:
        blockers.append("runner source must redact secrets")
    for env_name in FORBIDDEN_ENV_FALLBACKS:
        if _uses_forbidden_env_fallback(source, env_name):
            blockers.append(f"runner must not use forbidden env fallback {env_name}")
    for forbidden_call in (".create_profile_segment_template(", ".update_profile_segment_template(", ".delete_profile_segment_template("):
        if forbidden_call in source:
            blockers.append(f"runner must not call {forbidden_call}")
    for line in _executable_source_lines(source):
        upper = line.upper()
        for token in ("INSERT ", "UPDATE ", "DELETE "):
            if token in upper:
                blockers.append(f"runner contains SQL write token in executable source line: {line}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4R production read-only dry-run runner scope: {unexpected}")
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
        "runner_config": check_runner_config(data),
        "operations": check_operations(data),
        "evidence": check_evidence(data),
        "phase4s_recommendation": check_phase4s_recommendation(data),
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
        "# Phase 4R Profile Segment Template Production Read-Only Dry-Run Runner Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4R profile segment template production read-only dry-run runner.")
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
