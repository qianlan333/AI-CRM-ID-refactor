#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4am_action_templates_staging_owner_decision_package.md"
PLAN_YAML = ROOT / "docs/development/phase_4am_action_templates_staging_owner_decision_package.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"

REQUIRED_LABELS = {"owner-decision-required", "automerge-blocked"}
MISSING_OWNER_DECISIONS = {
    "automation_engine_owner_approval",
    "integration_gateway_owner_approval",
    "staging_db_config_owner_approval",
    "smoke_operator_assigned",
    "rollback_owner_assigned",
    "evidence_path_agreed",
    "write_smoke_approval_decision",
    "safe_namespace_cleanup_strategy_confirmed",
    "side_effect_safety_confirmed",
}
MISSING_CONFIG = {
    "repo_backend_sqlalchemy_confirmed",
    "staging_db_env_confirmed",
    "staging_db_url_safety_confirmed",
    "no_database_url_fallback_confirmed",
    "no_action_templates_database_url_fallback_confirmed",
    "no_test_database_url_fallback_confirmed",
    "read_only_evidence_path_confirmed",
    "write_evidence_path_confirmed_if_needed",
}
SAFE_OPTIONS = {
    "owner_approved_staging_smoke_evidence_after_all_closure_items_complete",
    "keep_action_templates_paused_and_select_different_low_risk_phase_4_package",
    "provide_partial_evidence_and_run_another_closure_update",
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
    "timer_execution_authorized",
    "outbound_send_authorized",
    "canary_approval_authorized",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4am_action_templates_staging_owner_decision_package.md",
    "docs/development/phase_4am_action_templates_staging_owner_decision_package.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4am_action_templates_staging_owner_decision_package.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4am_action_templates_staging_owner_decision_package.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
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
FORBIDDEN_DOC_CLAIMS = {
    "staging smoke executed",
    "production dry-run executed",
    "production approved",
    "canary approved",
    "delete_ready true",
    "delete_ready: true",
    "route_switch_ready=true",
    "autopilot-safe",
}


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value == "[]":
        return []
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
        if ":" not in text:
            index += 1
            continue
        key, raw_value = text.split(":", 1)
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            result[key.strip()] = _parse_scalar(raw_value)
        else:
            value, index = _parse_yaml_block(lines, index, indent + 2)
            result[key.strip()] = value
    return result, index


def load_yaml(path: Path = PLAN_YAML) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        data, _ = _parse_yaml_block(_yaml_lines(text), 0, 0)
        return data if isinstance(data, dict) else {}


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> tuple[set[str], list[str]]:
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


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    for path in (DOC, PLAN_YAML, STATE):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "warnings": warnings, "details": {}}

    data = load_yaml()
    state = load_yaml(STATE)

    if data.get("status") != "phase_4am_action_templates_staging_owner_decision_required":
        blockers.append("status must be phase_4am_action_templates_staging_owner_decision_required")
    package = data.get("package") if isinstance(data.get("package"), dict) else {}
    if package.get("type") != "owner_decision":
        blockers.append("package.type must be owner_decision")
    if package.get("auto_merge_allowed") is not False:
        blockers.append("owner decision package must not allow auto merge")
    if package.get("autopilot_safe_label_allowed") is not False:
        blockers.append("owner decision package must not allow autopilot-safe label")
    if not REQUIRED_LABELS <= set(package.get("required_labels") or []):
        blockers.append("owner decision package missing required labels")

    current = data.get("current_blocker") if isinstance(data.get("current_blocker"), dict) else {}
    if current.get("closure_items_still_pending") is not True:
        blockers.append("current_blocker.closure_items_still_pending must be true")
    if current.get("action_templates_status") != "awaiting_staging_approval_config":
        blockers.append("current_blocker.action_templates_status mismatch")

    if not MISSING_OWNER_DECISIONS <= set(data.get("missing_owner_decisions") or []):
        blockers.append("missing_owner_decisions incomplete")
    if not MISSING_CONFIG <= set(data.get("missing_config") or []):
        blockers.append("missing_config incomplete")
    if not SAFE_OPTIONS <= set(data.get("safe_next_options") or []):
        blockers.append("safe_next_options incomplete")

    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state.get("last_attempted_action") != state_update.get("last_attempted_action"):
        blockers.append("phase_execution_state.last_attempted_action must match owner decision package")
    if state.get("last_created_pr") != state_update.get("last_created_pr"):
        blockers.append("phase_execution_state.last_created_pr must match owner decision package")
    if state.get("recommended_next_pr") != state_update.get("recommended_next_pr"):
        blockers.append("phase_execution_state.recommended_next_pr must match owner decision package")
    if state.get("owner_approval_required") is not True:
        blockers.append("phase_execution_state.owner_approval_required must be true")
    if state.get("action_templates_readiness", {}).get("owner_decision_required") is not True:
        blockers.append("phase_execution_state action_templates_readiness.owner_decision_required must be true")

    next_action = data.get("next_action") if isinstance(data.get("next_action"), dict) else {}
    if next_action.get("user_must_choose_next_safe_path") is not True:
        blockers.append("next_action.user_must_choose_next_safe_path must be true")
    for field in ("production_dry_run_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "auto_merge_allowed"):
        if next_action.get(field) is not False:
            blockers.append(f"next_action.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for owner decision package: {unexpected}")
    protected = sorted(
        path
        for path in changed
        if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)
    )
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")

    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "details": {"changed_files": sorted(changed)},
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4AM Action Templates Staging Owner Decision Package Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
            "",
            "## Warnings",
            *(f"- {item}" for item in report["warnings"]),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = build_report()
    _write_outputs(report, args.output_json, args.output_md)
    print(f"overall: {report['overall']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
