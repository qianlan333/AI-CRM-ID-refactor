#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DOC = ROOT / "docs/development/phase_4ak_action_templates_staging_smoke_evidence.md"
YAML_DOC = ROOT / "docs/development/phase_4ak_action_templates_staging_smoke_evidence.yaml"
EVIDENCE_TOOL = ROOT / "tools/run_phase4ak_action_templates_staging_smoke_evidence.py"
LOWER_RUNNER = ROOT / "tools/run_phase4aj_action_templates_staging_smoke.py"
REQUIRED_DOCS = [DOC, YAML_DOC, EVIDENCE_TOOL, LOWER_RUNNER]
AUTH_FALSE_FIELDS = {
    "production_repository_route_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "production_write_authorized",
    "delete_ready",
}
REQUIRED_STATUSES = {
    "not_executed_missing_staging_db",
    "not_executed_missing_approval",
    "not_executed_db_url_safety_failed",
    "not_executed_missing_repo_backend",
    "not_executed_write_approval_missing",
    "staging_smoke_executed_readonly",
    "staging_smoke_executed_write_safe_namespace",
}
REQUIRED_READ_MATRIX = {"schema_available", "list_action_templates"}
REQUIRED_WRITE_MATRIX = {
    "create_with_idempotency",
    "idempotency_replay",
    "idempotency_conflict",
    "duplicate_template_code_rejected",
    "missing_name_rejected",
    "invalid_status_rejected",
    "dangerous_fields_rejected",
    "audit_event_emitted",
    "rollback_payload_present",
    "side_effect_safety_false",
}
REQUIRED_EXCLUDED_TRUE = {
    "generate_route_excluded",
    "from_workflow_route_excluded",
    "detail_route_excluded",
    "update_route_excluded",
    "delete_route_excluded",
    "deepseek_llm_adapter_excluded",
    "workflow_execution_excluded",
    "outbound_send_excluded",
    "wecom_openclaw_mcp_excluded",
}
OWNER_APPROVAL_FIELDS = {
    "automation_engine_owner",
    "integration_gateway_owner",
    "staging_db_config_owner",
    "rollback_owner",
    "smoke_operator",
}
ALLOWED_MARKERS = {"staging", "stage", "test", "local", "dev"}
FORBIDDEN_MARKERS = {"prod", "production", "primary", "master"}
ALLOWED_CHANGED_FILES = {
    "tools/run_phase4ak_action_templates_staging_smoke_evidence.py",
    "docs/development/phase_4ak_action_templates_staging_smoke_evidence.md",
    "docs/development/phase_4ak_action_templates_staging_smoke_evidence.yaml",
    "tools/check_phase4ak_action_templates_staging_smoke_evidence.py",
    "tests/test_phase4ak_action_templates_staging_smoke_evidence.py",
    "tools/run_phase4al_action_templates_staging_execution_preflight.py",
    "docs/development/phase_4al_action_templates_staging_execution_ready_gate.md",
    "docs/development/phase_4al_action_templates_staging_execution_ready_gate.yaml",
    "tools/check_phase4al_action_templates_staging_execution_ready_gate.py",
    "tests/test_phase4al_action_templates_staging_execution_ready_gate.py",
    "docs/development/phase_4am_action_templates_staging_wait_and_next_candidate.md",
    "docs/development/phase_4am_action_templates_staging_wait_and_next_candidate.yaml",
    "tools/check_phase4am_action_templates_staging_wait_and_next_candidate.py",
    "tests/test_phase4am_action_templates_staging_wait_and_next_candidate.py",
    "tools/check_phase4aj_action_templates_staging_smoke_package.py",
    "tools/check_phase4ai_action_templates_test_db_parity.py",
}
PROTECTED_EXACT = {
    "aicrm_next/main.py",
    "aicrm_next/production_compat/api.py",
    "app.py",
    "legacy_flask_app.py",
}
PROTECTED_PREFIXES = (
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "systemd/",
    "nginx/",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


def load_yaml(path: Path = YAML_DOC) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        return _load_yaml_without_dependency(text)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
    if data.get("status") != "phase_4ak_action_templates_staging_smoke_evidence_no_production_change":
        blockers.append("status must be phase_4ak_action_templates_staging_smoke_evidence_no_production_change")
    for field in sorted(AUTH_FALSE_FIELDS):
        if (data.get("authorizations") or {}).get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")
    tool = data.get("evidence_tool") or {}
    if tool.get("path") != "tools/run_phase4ak_action_templates_staging_smoke_evidence.py":
        blockers.append("evidence_tool.path must point to Phase 4AK evidence tool")
    if tool.get("mode") != "staging_smoke_evidence_gate":
        blockers.append("evidence_tool.mode must be staging_smoke_evidence_gate")
    if tool.get("may_call_lower_runner") is not True:
        blockers.append("evidence_tool.may_call_lower_runner must be true")
    if tool.get("lower_runner") != "tools/run_phase4aj_action_templates_staging_smoke.py":
        blockers.append("evidence_tool.lower_runner must point to Phase 4AJ runner")
    required_env = set(str(item) for item in _as_list(tool.get("required_env")))
    for env_name in ("AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL", "AICRM_ACTION_TEMPLATES_REPO_BACKEND", "AICRM_PHASE4AK_STAGING_SMOKE_APPROVED"):
        if env_name not in required_env:
            blockers.append(f"evidence_tool.required_env must include {env_name}")
    if "AICRM_PHASE4AK_STAGING_WRITE_APPROVED" not in _as_list(tool.get("write_approval_env")):
        blockers.append("evidence_tool.write_approval_env must include AICRM_PHASE4AK_STAGING_WRITE_APPROVED")
    fallbacks = set(str(item) for item in _as_list(tool.get("forbidden_env_fallbacks")))
    for env_name in ("DATABASE_URL", "AICRM_ACTION_TEMPLATES_DATABASE_URL", "AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL"):
        if env_name not in fallbacks:
            blockers.append(f"evidence_tool.forbidden_env_fallbacks must include {env_name}")
    if not ALLOWED_MARKERS <= {str(item) for item in _as_list(tool.get("db_url_allowed_markers"))}:
        blockers.append("evidence_tool.db_url_allowed_markers incomplete")
    if not FORBIDDEN_MARKERS <= {str(item) for item in _as_list(tool.get("db_url_forbidden_markers"))}:
        blockers.append("evidence_tool.db_url_forbidden_markers incomplete")
    if tool.get("production_data_allowed") is not False:
        blockers.append("evidence_tool.production_data_allowed must be false")
    if tool.get("route_owner_change_allowed") is not False:
        blockers.append("evidence_tool.route_owner_change_allowed must be false")
    if not REQUIRED_STATUSES <= set(str(item) for item in _as_list(data.get("result_statuses"))):
        blockers.append("result_statuses incomplete")
    namespace = data.get("safe_namespace") or {}
    if namespace.get("template_code_prefix") != "phase4aj_staging_smoke_":
        blockers.append("safe_namespace.template_code_prefix must be phase4aj_staging_smoke_")
    if namespace.get("operator") != "phase4aj_staging_smoke_operator":
        blockers.append("safe_namespace.operator must be phase4aj_staging_smoke_operator")
    if namespace.get("idempotency_key_prefix") != "phase4aj_staging_smoke_":
        blockers.append("safe_namespace.idempotency_key_prefix must be phase4aj_staging_smoke_")
    if namespace.get("delete_required") is not False:
        blockers.append("safe_namespace.delete_required must be false")
    matrix = data.get("evidence_matrix") or {}
    if not REQUIRED_READ_MATRIX <= set(_as_list(matrix.get("read"))):
        blockers.append("evidence_matrix.read incomplete")
    if not REQUIRED_WRITE_MATRIX <= set(_as_list(matrix.get("write"))):
        blockers.append("evidence_matrix.write incomplete")
    excluded = data.get("excluded") or {}
    for field in sorted(REQUIRED_EXCLUDED_TRUE):
        if excluded.get(field) is not True:
            blockers.append(f"excluded.{field} must be true")
    approval = data.get("owner_approval") or {}
    for field in sorted(OWNER_APPROVAL_FIELDS):
        if approval.get(field) != "pending":
            blockers.append(f"owner_approval.{field} must be pending")
    recommendation = data.get("phase_4al_recommendation") or {}
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_4al_recommendation.recommended_next_step missing")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if recommendation.get(field) is not False:
            blockers.append(f"phase_4al_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_evidence_tool_static() -> dict[str, Any]:
    blockers: list[str] = []
    text = _read(EVIDENCE_TOOL)
    for token in (
        "--output-json",
        "--output-md",
        "AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL",
        "AICRM_ACTION_TEMPLATES_REPO_BACKEND",
        "AICRM_PHASE4AK_STAGING_SMOKE_APPROVED",
        "AICRM_PHASE4AK_STAGING_WRITE_APPROVED",
        "run_phase4aj_action_templates_staging_smoke",
    ):
        if token not in text:
            blockers.append(f"evidence tool missing token: {token}")
    for forbidden in (
        'os.getenv("DATABASE_URL"',
        "os.getenv('DATABASE_URL'",
        'os.environ.get("DATABASE_URL"',
        "os.environ.get('DATABASE_URL'",
        'os.getenv("AICRM_ACTION_TEMPLATES_DATABASE_URL"',
        "os.getenv('AICRM_ACTION_TEMPLATES_DATABASE_URL'",
        'os.getenv("AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL"',
        "os.getenv('AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL'",
        "get_settings().database_url",
        "shared.database",
        "wecom_ability_service",
        "DeepSeek",
        "deepseek",
        "llm_adapter",
        "action-templates/generate",
        "action-templates/from-workflow",
        ".delete(",
        ".put(",
        "update_action_template",
        "delete_action_template",
    ):
        if forbidden in text:
            blockers.append(f"evidence tool contains forbidden token: {forbidden}")
    for marker in FORBIDDEN_MARKERS:
        if marker not in text:
            blockers.append(f"evidence tool must reject marker: {marker}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_optional_probe() -> dict[str, Any]:
    warnings: list[str] = []
    blockers: list[str] = []
    try:
        import tools.run_phase4ak_action_templates_staging_smoke_evidence as runner
    except ModuleNotFoundError as exc:
        blockers.append(f"evidence tool import failed: {exc}")
        return {"ok": False, "blockers": blockers, "warnings": warnings}
    report = runner.run_runner()
    if os.getenv("AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL") and os.getenv("AICRM_PHASE4AK_STAGING_SMOKE_APPROVED"):
        if not report.get("ok"):
            blockers.append(f"staging evidence probe failed: {report.get('result_status')}")
    else:
        allowed_blocked = {
            "not_executed_missing_staging_db",
            "not_executed_missing_approval",
            "not_executed_missing_repo_backend",
            "not_executed_db_url_safety_failed",
        }
        if report.get("result_status") not in allowed_blocked or report.get("lower_runner_called") is not False:
            blockers.append("missing gate conditions must produce blocked evidence without calling lower runner")
        warnings.append(f"staging smoke evidence not executed: {report.get('result_status')}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "runner_result_status": report.get("result_status")}


def _is_protected(path: str) -> bool:
    return path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4AK scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    for blocked in ("aicrm_next/main.py", "aicrm_next/production_compat/api.py"):
        if blocked in changed:
            blockers.append(f"{blocked} must remain unchanged")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_doc_claims() -> dict[str, Any]:
    text = _read(DOC).lower()
    blockers: list[str] = []
    for pattern in (
        r"production parity",
        r"production repository enabled as route owner",
        r"production write authorized",
        r"route switch authorized",
        r"fallback removal authorized",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ):
        if re.search(pattern, text):
            blockers.append(f"doc appears to claim forbidden state: {pattern}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def build_report() -> dict[str, Any]:
    data = load_yaml()
    checks = {
        "required_docs": check_required_docs(),
        "yaml_contract": check_yaml_contract(data),
        "evidence_tool_static": check_evidence_tool_static(),
        "optional_probe": check_optional_probe(),
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
        "# Phase 4AK Action Templates Staging Smoke Evidence Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4AK action templates staging smoke evidence gate.")
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
