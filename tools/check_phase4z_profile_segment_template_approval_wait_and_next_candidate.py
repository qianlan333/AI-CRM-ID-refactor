#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.md"
PLAN_YAML = ROOT / "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.yaml"
REQUIRED_DOCS = [
    DOC,
    PLAN_YAML,
    ROOT / "docs/development/phase_4y_profile_segment_template_production_readonly_preflight.md",
    ROOT / "docs/development/phase_4x_profile_segment_template_production_readonly_final_gate.md",
]
COMPLETED_ASSETS = {
    "next_native_contract",
    "companion_schema",
    "sql_alchemy_adapter_behind_flag",
    "local_test_db_parity_harness",
    "staging_smoke_package",
    "production_readonly_runner",
    "production_readonly_preflight",
    "final_gate",
}
PROFILE_BLOCKERS = {
    "owner_approval_missing",
    "production_config_review_missing",
    "production_db_env_not_confirmed",
    "read_only_no_write_flags_not_confirmed",
    "rollback_owner_not_assigned",
    "evidence_path_not_agreed",
    "fallback_validation_plan_not_confirmed",
}
RESUME_CONDITIONS = {
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
AUTH_FALSE_FIELDS = {
    "production_dry_run_execution_authorized",
    "production_data_connection_authorized",
    "production_write_authorized",
    "production_repository_route_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "delete_ready",
}
FORBIDDEN_SCOPE_TERMS = (
    "payment",
    "oauth",
    "wecom external",
    "callback",
    "run-due",
    "timer",
    "execution",
    "send",
    "upload",
    "openclaw",
    "mcp",
    "public submit",
    "external push",
)
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.md",
    "docs/development/phase_4z_profile_segment_template_approval_wait_and_next_candidate.yaml",
    "tools/check_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
    "tests/test_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
    "tools/check_phase4y_profile_segment_template_production_readonly_preflight.py",
    "tools/check_phase4x_profile_segment_template_production_readonly_final_gate.py",
    "tools/check_phase4w_profile_segment_template_production_readonly_execution_ready_gate.py",
    "tools/check_phase4v_profile_segment_template_production_readonly_execution_blocker_and_readiness.py",
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
    "profile-segment-template production dry-run executed",
    "production route switch authorized",
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


def _list_values(value: Any) -> set[str]:
    return {str(item) for item in _as_list(value)}


def _item_list(value: Any) -> list[str]:
    result: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            result.append(str(item.get("item", "")))
        else:
            result.append(str(item))
    return [item for item in result if item]


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


def check_profile_segment_template(data: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = (data or load_yaml()).get("profile_segment_template") or {}
    blockers: list[str] = []
    if profile.get("status") != "awaiting_production_approval_config":
        blockers.append("profile_segment_template.status must be awaiting_production_approval_config")
    for field in (
        "production_dry_run_executed",
        "production_route_owner_switch_authorized",
        "fallback_removal_authorized",
        "production_write_authorized",
        "delete_ready",
    ):
        if profile.get(field) is not False:
            blockers.append(f"profile_segment_template.{field} must be false")
    missing_assets = sorted(COMPLETED_ASSETS - _list_values(profile.get("completed_assets")))
    if missing_assets:
        blockers.append(f"profile_segment_template.completed_assets missing {missing_assets}")
    missing_blockers = sorted(PROFILE_BLOCKERS - _list_values(profile.get("blockers")))
    if missing_blockers:
        blockers.append(f"profile_segment_template.blockers missing {missing_blockers}")
    missing_resume = sorted(RESUME_CONDITIONS - _list_values(profile.get("resume_conditions")))
    if missing_resume:
        blockers.append(f"profile_segment_template.resume_conditions missing {missing_resume}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_next_candidate(data: dict[str, Any] | None = None) -> dict[str, Any]:
    candidate = (data or load_yaml()).get("next_candidate") or {}
    blockers: list[str] = []
    if not candidate.get("selected_route_family"):
        blockers.append("next_candidate.selected_route_family must be non-empty")
    if not candidate.get("capability_owner"):
        blockers.append("next_candidate.capability_owner must be non-empty")
    if candidate.get("replacement_phase") != "phase_4_internal_write":
        blockers.append("next_candidate.replacement_phase must be phase_4_internal_write")
    if candidate.get("replacement_category") not in {"internal_write", "shell_or_navigation", "readonly"}:
        blockers.append("next_candidate.replacement_category must be internal_write, shell_or_navigation, or readonly")
    for field in ("excluded_side_effects", "required_guardrails", "phase_4aa_scope", "risks"):
        if not _item_list(candidate.get(field)):
            blockers.append(f"next_candidate.{field} must be non-empty")
    for field in ("rollback_requirement", "business_continuity_requirement"):
        if not candidate.get(field):
            blockers.append(f"next_candidate.{field} must be non-empty")
    scope_text = " ".join(
        [
            str(candidate.get("selected_route_family") or ""),
            str(candidate.get("why_selected") or ""),
            " ".join(_item_list(candidate.get("required_guardrails"))),
            " ".join(_item_list(candidate.get("phase_4aa_scope"))),
            " ".join(_item_list(candidate.get("risks"))),
            str(candidate.get("rollback_requirement") or ""),
            str(candidate.get("business_continuity_requirement") or ""),
        ]
    ).lower()
    for term in FORBIDDEN_SCOPE_TERMS:
        if term in scope_text:
            blockers.append(f"next_candidate actual scope contains forbidden high-risk term: {term}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_authorizations(data: dict[str, Any] | None = None) -> dict[str, Any]:
    auth = (data or load_yaml()).get("authorizations") or {}
    blockers = [
        f"authorizations.{field} must be false"
        for field in sorted(AUTH_FALSE_FIELDS)
        if auth.get(field) is not False
    ]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase_4aa_recommendation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = (data or load_yaml()).get("phase_4aa_recommendation") or {}
    blockers: list[str] = []
    if not rec.get("recommended_next_step"):
        blockers.append("phase_4aa_recommendation.recommended_next_step missing")
    for field in (
        "production_write_allowed",
        "production_route_switch_allowed",
        "fallback_removal_allowed",
        "production_write_canary_allowed",
    ):
        if rec.get(field) is not False:
            blockers.append(f"phase_4aa_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4Z scope: {unexpected}")
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
        "profile_segment_template": check_profile_segment_template(data),
        "next_candidate": check_next_candidate(data),
        "authorizations": check_authorizations(data),
        "phase_4aa_recommendation": check_phase_4aa_recommendation(data),
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
        "# Phase 4Z Profile Segment Template Approval-Wait And Next Candidate Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4Z profile segment template approval-wait handoff and next candidate.")
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
