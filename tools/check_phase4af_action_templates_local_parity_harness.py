#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PLAN_MD = ROOT / "docs/development/phase_4af_action_templates_local_parity_harness.md"
PLAN_YAML = ROOT / "docs/development/phase_4af_action_templates_local_parity_harness.yaml"
HARNESS = ROOT / "tools/run_phase4af_action_templates_local_parity.py"
MAIN = ROOT / "aicrm_next/main.py"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
REQUIRED_DOCS = [PLAN_MD, PLAN_YAML, HARNESS]
AUTH_FALSE_FIELDS = {
    "production_repository_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "production_write_authorized",
    "delete_ready",
}
REQUIRED_READ_MATRIX = {
    "list_ok",
    "deterministic_fixture_seed",
    "side_effect_safety_present",
}
REQUIRED_CREATE_MATRIX = {
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
    "production_fixture_write_blocked",
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
ALLOWED_CHANGED_FILES = {
    "tools/run_phase4af_action_templates_local_parity.py",
    "docs/development/phase_4af_action_templates_local_parity_harness.md",
    "docs/development/phase_4af_action_templates_local_parity_harness.yaml",
    "tools/check_phase4af_action_templates_local_parity_harness.py",
    "tests/test_phase4af_action_templates_local_parity_harness.py",
    "tools/check_phase4ae_action_templates_native_fixture_contract.py",
    "tools/check_phase4ad_action_templates_companion_migration.py",
    "tools/check_phase4ac_action_templates_companion_schema_plan.py",
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


def load_yaml(path: Path = PLAN_YAML) -> dict[str, Any]:
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
    if data.get("status") != "phase_4af_action_templates_local_parity_harness_no_production_change":
        blockers.append("status must be phase_4af_action_templates_local_parity_harness_no_production_change")
    authorizations = data.get("authorizations") or {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")
    harness = data.get("harness") or {}
    if harness.get("path") != "tools/run_phase4af_action_templates_local_parity.py":
        blockers.append("harness.path must point to Phase 4AF harness")
    if not (ROOT / str(harness.get("path") or "")).exists():
        blockers.append("harness.path does not exist")
    for field in ("db_connection_allowed", "legacy_service_call_allowed", "external_call_allowed"):
        if harness.get(field) is not False:
            blockers.append(f"harness.{field} must be false")
    if harness.get("fixture_evidence_only") is not True:
        blockers.append("harness.fixture_evidence_only must be true")

    matrix = data.get("harness_matrix") or {}
    read_items = {str(item) for item in _as_list(matrix.get("read"))}
    create_items = {str(item) for item in _as_list(matrix.get("create"))}
    missing_read = sorted(REQUIRED_READ_MATRIX - read_items)
    missing_create = sorted(REQUIRED_CREATE_MATRIX - create_items)
    if missing_read:
        blockers.append(f"harness_matrix.read missing {missing_read}")
    if missing_create:
        blockers.append(f"harness_matrix.create missing {missing_create}")

    excluded = data.get("excluded") or {}
    for field in sorted(REQUIRED_EXCLUDED_TRUE):
        if excluded.get(field) is not True:
            blockers.append(f"excluded.{field} must be true")

    readiness = data.get("phase_4ag_readiness") or {}
    if readiness.get("local_parity_required") is not True:
        blockers.append("phase_4ag_readiness.local_parity_required must be true")
    if readiness.get("production_adapter_planning_allowed_after_local_parity") is not True:
        blockers.append("phase_4ag_readiness.production_adapter_planning_allowed_after_local_parity must be true")
    for field in ("production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if readiness.get(field) is not False:
            blockers.append(f"phase_4ag_readiness.{field} must be false")

    recommendation = data.get("phase_4ag_recommendation") or {}
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_4ag_recommendation.recommended_next_step missing")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if recommendation.get(field) is not False:
            blockers.append(f"phase_4ag_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_harness_static() -> dict[str, Any]:
    text = _read(HARNESS)
    blockers: list[str] = []
    for required in ("--output-json", "--output-md"):
        if required not in text:
            blockers.append(f"harness missing CLI arg {required}")
    forbidden_tokens = [
        "wecom_ability_service",
        "DeepSeek",
        "deepseek",
        "LLM",
        "llm_adapter",
        "action-templates/generate",
        "action-templates/from-workflow",
        "create_engine",
        "DATABASE_URL",
        "psycopg",
        "sqlalchemy",
    ]
    for token in forbidden_tokens:
        if token in text:
            blockers.append(f"harness contains forbidden token: {token}")
    route_calls = re.findall(r"\.([a-z]+)\(\s*ROUTE", text)
    disallowed_methods = sorted({method for method in route_calls if method.lower() not in {"get", "post"}})
    if disallowed_methods:
        blockers.append(f"harness uses disallowed methods against action-template route: {disallowed_methods}")
    if ".put(" in text or ".delete(" in text:
        blockers.append("harness must not call update/delete routes")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_fastapi_probe() -> dict[str, Any]:
    warnings: list[str] = []
    blockers: list[str] = []
    try:
        import tools.run_phase4af_action_templates_local_parity as harness  # type: ignore
    except ModuleNotFoundError as exc:
        warnings.append(f"FastAPI harness probe skipped: {exc}")
        return {"ok": True, "blockers": [], "warnings": warnings}
    report = harness.run_harness()
    if not report.get("ok"):
        blockers.append(f"harness report failed: {report.get('details')}")
    expected_names = REQUIRED_READ_MATRIX | REQUIRED_CREATE_MATRIX | {"idempotency_replay", "idempotency_conflict", "dangerous_fields_rejected"}
    passed_names = {str(item.get("name")) for item in _as_list(report.get("details")) if isinstance(item, dict) and item.get("status") == "passed"}
    missing = sorted(expected_names - passed_names)
    if missing and report.get("skipped", 0) == 0:
        blockers.append(f"harness probe missing passed matrix items: {missing}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "report": report}


def _is_protected(path: str) -> bool:
    if path in PROTECTED_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def check_change_scope() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    protected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES and _is_protected(path))
    blockers: list[str] = []
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4AF scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    for blocked in ("aicrm_next/main.py", "aicrm_next/production_compat/api.py"):
        if blocked in changed:
            blockers.append(f"{blocked} must remain unchanged")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_doc_claims() -> dict[str, Any]:
    text = _read(PLAN_MD).lower()
    blockers: list[str] = []
    for pattern in (
        r"production parity",
        r"production repository enabled",
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
        "harness_static": check_harness_static(),
        "fastapi_probe": check_fastapi_probe(),
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
        "# Phase 4AF Action Templates Local Parity Harness Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4AF action templates local fixture parity harness.")
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
