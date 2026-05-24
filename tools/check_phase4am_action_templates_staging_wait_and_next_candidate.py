#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4am_action_templates_staging_wait_and_next_candidate.md"
PLAN_YAML = ROOT / "docs/development/phase_4am_action_templates_staging_wait_and_next_candidate.yaml"
REQUIRED_DOCS = [DOC, PLAN_YAML]
COMPLETED_ASSETS = {
    "schema_route_service_confirmation",
    "companion_schema_planning",
    "additive_companion_migration_artifact",
    "fixture_native_contract",
    "local_fixture_parity_harness",
    "sql_alchemy_adapter_behind_flag",
    "local_test_db_adapter_parity_harness",
    "staging_smoke_package",
    "staging_smoke_evidence_gate",
    "staging_execution_readiness_gate",
}
BLOCKERS = {
    "staging_db_config_owner_approval_missing",
    "staging_db_env_not_confirmed",
    "staging_db_url_safety_not_confirmed",
    "smoke_operator_not_assigned",
    "rollback_owner_not_assigned",
    "evidence_path_not_agreed",
    "write_smoke_approval_not_confirmed",
    "safe_namespace_cleanup_strategy_not_confirmed",
}
RESUME_CONDITIONS = {
    "automation_engine_owner_approval",
    "integration_gateway_owner_approval",
    "staging_db_config_owner_approval",
    "rollback_owner_assigned",
    "smoke_operator_assigned",
    "staging_db_env_confirmed",
    "staging_db_url_safety_confirmed",
    "repo_backend_confirmed",
    "read_only_preflight_confirmed",
    "write_smoke_approval_confirmed_if_needed",
    "safe_namespace_confirmed",
    "evidence_path_confirmed",
    "cleanup_strategy_confirmed",
    "side_effect_safety_confirmed",
}
AUTH_FALSE_FIELDS = {
    "staging_smoke_execution_authorized",
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
    "docs/development/phase_4am_action_templates_staging_wait_and_next_candidate.md",
    "docs/development/phase_4am_action_templates_staging_wait_and_next_candidate.yaml",
    "tools/check_phase4am_action_templates_staging_wait_and_next_candidate.py",
    "tests/test_phase4am_action_templates_staging_wait_and_next_candidate.py",
    "tools/check_phase4al_action_templates_staging_execution_ready_gate.py",
    "tools/check_phase4ak_action_templates_staging_smoke_evidence.py",
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
    "action-templates staging smoke executed",
    "production dry-run executed",
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


def _items(values: list[Any]) -> set[str]:
    result: set[str] = set()
    for item in values:
        result.add(str(item.get("item") if isinstance(item, dict) else item).lower())
    return result


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return False, proc.stdout, proc.stderr
    return True, proc.stdout, proc.stderr


def _changed_files_from_git() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only", "--cached"]):
        ok, stdout, stderr = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
        else:
            warnings.append(f"git {' '.join(args)} unavailable: {(stderr or stdout).strip()}")
    ok, stdout, stderr = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    else:
        warnings.append(f"git ls-files --others unavailable: {(stderr or stdout).strip()}")
    return changed, warnings


def check_required_docs() -> dict[str, Any]:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_DOCS if not path.exists()]
    return {"ok": not missing, "blockers": [f"missing required artifact: {path}" for path in missing], "warnings": []}


def check_yaml_contract(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if data.get("status") != "phase_4am_staging_wait_and_next_candidate_no_runtime_change":
        blockers.append("status must be phase_4am_staging_wait_and_next_candidate_no_runtime_change")
    action = data.get("action_templates") or {}
    if action.get("status") != "awaiting_staging_approval_config":
        blockers.append("action_templates.status must be awaiting_staging_approval_config")
    for field in ("staging_smoke_executed", "production_route_owner_switch_authorized", "fallback_removal_authorized", "production_write_authorized", "delete_ready"):
        if action.get(field) is not False:
            blockers.append(f"action_templates.{field} must be false")
    if not COMPLETED_ASSETS <= set(action.get("completed_assets") or []):
        blockers.append("action_templates.completed_assets incomplete")
    if not BLOCKERS <= set(action.get("blockers") or []):
        blockers.append("action_templates.blockers incomplete")
    if not RESUME_CONDITIONS <= set(action.get("resume_conditions") or []):
        blockers.append("action_templates.resume_conditions incomplete")
    candidate = data.get("next_candidate") or {}
    if not candidate.get("selected_route_family"):
        blockers.append("next_candidate.selected_route_family missing")
    if not candidate.get("capability_owner"):
        blockers.append("next_candidate.capability_owner missing")
    if candidate.get("replacement_phase") != "phase_4_internal_write":
        blockers.append("next_candidate.replacement_phase must be phase_4_internal_write")
    if candidate.get("replacement_category") not in {"internal_write", "shell_or_navigation", "readonly"}:
        blockers.append("next_candidate.replacement_category invalid")
    for field in ("excluded_side_effects", "required_guardrails", "phase_4an_scope", "risks"):
        if not candidate.get(field):
            blockers.append(f"next_candidate.{field} missing")
    for field in ("rollback_requirement", "business_continuity_requirement"):
        if not candidate.get(field):
            blockers.append(f"next_candidate.{field} missing")
    excluded = _items(candidate.get("excluded_side_effects") or [])
    allowed_scope_text = " ".join(
        str(candidate.get(field, "")).lower()
        for field in ("selected_route_family", "capability_owner", "replacement_phase", "replacement_category", "why_selected", "rollback_requirement", "business_continuity_requirement")
    )
    allowed_scope_text += " " + " ".join(_items(candidate.get("required_guardrails") or []))
    allowed_scope_text += " " + " ".join(_items(candidate.get("phase_4an_scope") or []))
    allowed_scope_text += " " + " ".join(_items(candidate.get("risks") or []))
    for term in FORBIDDEN_SCOPE_TERMS:
        if term in allowed_scope_text and term not in excluded:
            blockers.append(f"next_candidate actual scope contains forbidden term: {term}")
    for field in sorted(AUTH_FALSE_FIELDS):
        if (data.get("authorizations") or {}).get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")
    recommendation = data.get("phase_4an_recommendation") or {}
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_4an_recommendation.recommended_next_step missing")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if recommendation.get(field) is not False:
            blockers.append(f"phase_4an_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4AM scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_doc_claims() -> dict[str, Any]:
    text = _read(DOC).lower()
    blockers = [f"doc appears to claim forbidden state: {phrase}" for phrase in FORBIDDEN_DOC_PHRASES if phrase in text]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def build_report() -> dict[str, Any]:
    data = load_yaml()
    checks = {
        "required_docs": check_required_docs(),
        "yaml_contract": check_yaml_contract(data),
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
        "# Phase 4AM Action Templates Staging Wait And Next Candidate Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4AM action templates staging wait and next candidate.")
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
