#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN_MD = ROOT / "docs/development/phase_4ae_action_templates_native_fixture_contract.md"
PLAN_YAML = ROOT / "docs/development/phase_4ae_action_templates_native_fixture_contract.yaml"
API = ROOT / "aicrm_next/automation_engine/api.py"
APP = ROOT / "aicrm_next/automation_engine/application.py"
DOMAIN = ROOT / "aicrm_next/automation_engine/action_templates.py"
REPO = ROOT / "aicrm_next/automation_engine/action_template_repository.py"
MAIN = ROOT / "aicrm_next/main.py"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
REQUIRED_DOCS = [PLAN_MD, PLAN_YAML]
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
EXPECTED_IMPLEMENTED_ROUTES = {
    ("GET", "/api/admin/automation-conversion/action-templates"),
    ("POST", "/api/admin/automation-conversion/action-templates"),
}
REQUIRED_EXCLUDED_ROUTES = {
    "/api/admin/automation-conversion/action-templates/generate",
    "/api/admin/automation-conversion/action-templates/from-workflow",
    "/api/admin/automation-conversion/action-templates/{template_id}",
}
CONTRACT_FEATURES = {
    "deterministic_fixture_seed",
    "create_idempotency",
    "idempotency_conflict",
    "duplicate_template_code_protection",
    "audit_event",
    "rollback_payload",
    "dangerous_fields_rejected",
    "side_effect_safety",
    "production_fixture_success_blocked",
}
SIDE_EFFECT_FALSE_FIELDS = {
    "real_external_call_allowed",
    "automation_execution_allowed",
    "outbound_send_allowed",
    "wecom_call_allowed",
    "openclaw_call_allowed",
    "mcp_call_allowed",
    "llm_call_allowed",
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/automation_engine/api.py",
    "aicrm_next/automation_engine/application.py",
    "aicrm_next/automation_engine/dto.py",
    "aicrm_next/automation_engine/repo.py",
    "aicrm_next/automation_engine/action_templates.py",
    "aicrm_next/automation_engine/action_template_repository.py",
    "docs/development/phase_4ae_action_templates_native_fixture_contract.md",
    "docs/development/phase_4ae_action_templates_native_fixture_contract.yaml",
    "tools/check_phase4ae_action_templates_native_fixture_contract.py",
    "tests/test_phase4ae_action_templates_native_fixture_contract.py",
    "tools/check_phase4ad_action_templates_companion_migration.py",
    "tools/check_phase4ac_action_templates_companion_schema_plan.py",
    "tools/check_phase4ab_action_templates_schema_confirmation.py",
    "tools/run_phase4af_action_templates_local_parity.py",
    "docs/development/phase_4af_action_templates_local_parity_harness.md",
    "docs/development/phase_4af_action_templates_local_parity_harness.yaml",
    "tools/check_phase4af_action_templates_local_parity_harness.py",
    "tests/test_phase4af_action_templates_local_parity_harness.py",
    "docs/development/phase_4ag_action_templates_repository_adapter_plan.md",
    "docs/development/phase_4ag_action_templates_repository_adapter_plan.yaml",
    "tools/check_phase4ag_action_templates_repository_adapter_plan.py",
    "tests/test_phase4ag_action_templates_repository_adapter_plan.py",
    "aicrm_next/automation_engine/action_template_sqlalchemy_repository.py",
    "docs/development/phase_4ah_action_templates_repository_adapter.md",
    "docs/development/phase_4ah_action_templates_repository_adapter.yaml",
    "tools/check_phase4ah_action_templates_repository_adapter.py",
    "tests/test_phase4ah_action_templates_repository_adapter.py",
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
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
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
    return {"ok": not missing, "blockers": [f"missing required doc: {path}" for path in missing], "warnings": []}


def check_yaml_contract(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data or load_yaml()
    blockers: list[str] = []
    if data.get("status") != "phase_4ae_action_templates_native_fixture_contract_no_production_change":
        blockers.append("status must be phase_4ae_action_templates_native_fixture_contract_no_production_change")
    authorizations = data.get("authorizations") or {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    implemented = {
        (str(route.get("method") or ""), str(route.get("path") or ""))
        for route in _as_list(data.get("implemented_routes"))
        if isinstance(route, dict)
    }
    if implemented != EXPECTED_IMPLEMENTED_ROUTES:
        blockers.append(f"implemented_routes must be exactly {sorted(EXPECTED_IMPLEMENTED_ROUTES)}")

    excluded = {
        str(route.get("path") or "")
        for route in _as_list(data.get("excluded_routes"))
        if isinstance(route, dict)
    }
    missing_excluded = sorted(REQUIRED_EXCLUDED_ROUTES - excluded)
    if missing_excluded:
        blockers.append(f"excluded_routes missing {missing_excluded}")

    features = data.get("contract_features") or {}
    for field in sorted(CONTRACT_FEATURES):
        if features.get(field) is not True:
            blockers.append(f"contract_features.{field} must be true")

    safety = data.get("side_effect_safety") or {}
    for field in sorted(SIDE_EFFECT_FALSE_FIELDS):
        if safety.get(field) is not False:
            blockers.append(f"side_effect_safety.{field} must be false")

    recommendation = data.get("phase_4af_recommendation") or {}
    if not recommendation.get("recommended_next_step"):
        blockers.append("phase_4af_recommendation.recommended_next_step missing")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if recommendation.get(field) is not False:
            blockers.append(f"phase_4af_recommendation.{field} must be false")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _route_decorators() -> set[tuple[str, str]]:
    text = _read(API)
    routes: set[tuple[str, str]] = set()
    for method, path in re.findall(r"@router\.(get|post|put|delete)\(\"([^\"]+)\"", text):
        if "action-templates" in path:
            routes.add((method.upper(), path))
    return routes


def check_static_code() -> dict[str, Any]:
    blockers: list[str] = []
    api_text = _read(API)
    app_text = _read(APP)
    domain_text = _read(DOMAIN)
    repo_text = _read(REPO)
    combined = "\n".join([api_text, app_text, domain_text, repo_text])

    if "wecom_ability_service" in combined:
        blockers.append("action-template native contract must not import wecom_ability_service")
    for token in ("DeepSeek", "deepseek", "LLM", "llm_adapter", "call_deepseek"):
        if token in api_text or token in app_text or token in repo_text:
            blockers.append(f"forbidden adapter token in action-template contract: {token}")
    routes = _route_decorators()
    if routes != EXPECTED_IMPLEMENTED_ROUTES:
        blockers.append(f"action-template API routes must be exactly GET/POST list/create, got {sorted(routes)}")
    for forbidden in ("action-templates/generate", "action-templates/from-workflow"):
        if forbidden in api_text:
            blockers.append(f"forbidden action-template route implemented: {forbidden}")
    if "delete_action_template" in api_text or re.search(r"@router\.delete\(.*action-templates", api_text):
        blockers.append("DELETE action-template route must not be implemented")
    for required in ("ActionTemplateCreateRequest", "ListActionTemplatesQuery", "CreateActionTemplateCommand"):
        if required not in api_text + app_text:
            blockers.append(f"missing native contract symbol: {required}")
    for required in ("idempotency", "audit", "rollback_payload", "ActionTemplateIdempotencyConflict"):
        if required not in repo_text:
            blockers.append(f"repository missing required behavior marker: {required}")
    for dangerous in ("run_due", "deepseek", "llm", "agent_runtime_execution"):
        if dangerous not in domain_text:
            blockers.append(f"dangerous field rejection missing token: {dangerous}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def _all_real_safety_false(payload: dict[str, Any]) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def check_fastapi_probe() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    old_env = {
        key: os.environ.get(key)
        for key in (
            "AICRM_NEXT_ENV",
            "DATABASE_URL",
            "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE",
            "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE",
        )
    }
    try:
        try:
            from fastapi.testclient import TestClient  # type: ignore
            from aicrm_next.automation_engine.action_template_repository import reset_action_template_fixture_state
            from aicrm_next.main import create_app
        except ModuleNotFoundError as exc:
            warnings.append(f"fastapi probe skipped: {exc}")
            return {"ok": True, "blockers": [], "warnings": warnings}

        os.environ["AICRM_NEXT_ENV"] = "test"
        os.environ.pop("DATABASE_URL", None)
        os.environ["AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"] = "0"
        os.environ["AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE"] = "1"
        reset_action_template_fixture_state()
        client = TestClient(create_app(), raise_server_exceptions=False)

        listed = client.get("/api/admin/automation-conversion/action-templates")
        if listed.status_code != 200:
            blockers.append(f"GET list expected 200, got {listed.status_code}: {listed.text}")
        else:
            body = listed.json()
            if body.get("route_owner") != "ai_crm_next" or body.get("source_status") != "fixture_local_contract":
                blockers.append("GET list must return Next owner and fixture/local source_status")
            if not _all_real_safety_false(body):
                blockers.append("GET list side_effect_safety must be all false")

        payload = {
            "template_name": "Phase 4AE Probe",
            "template_code": "phase4ae_probe",
            "idempotency_key": "phase4ae-probe",
            "operator": "checker",
        }
        created = client.post("/api/admin/automation-conversion/action-templates", json=payload)
        if created.status_code != 201:
            blockers.append(f"POST create expected 201, got {created.status_code}: {created.text}")
        else:
            body = created.json()
            if body.get("template", {}).get("template_code") != "phase4ae_probe":
                blockers.append("POST create response missing created template")
            if body.get("rollback_payload") is None or body.get("audit_event") is None:
                blockers.append("POST create must include rollback_payload and audit_event")
            if not _all_real_safety_false(body):
                blockers.append("POST create side_effect_safety must be all false")

        replay = client.post("/api/admin/automation-conversion/action-templates", json=payload)
        if replay.status_code != 201 or replay.json().get("idempotent_replay") is not True:
            blockers.append("idempotency replay must return stored response with idempotent_replay true")

        conflict_payload = {**payload, "template_name": "Phase 4AE Probe Conflict"}
        conflict = client.post("/api/admin/automation-conversion/action-templates", json=conflict_payload)
        if conflict.status_code != 409:
            blockers.append(f"idempotency conflict expected 409, got {conflict.status_code}: {conflict.text}")

        dangerous = client.post(
            "/api/admin/automation-conversion/action-templates",
            json={"template_name": "Danger", "idempotency_key": "danger", "default_config": {"run_due": True}},
        )
        if dangerous.status_code != 400:
            blockers.append(f"dangerous field rejection expected 400, got {dangerous.status_code}: {dangerous.text}")

        os.environ["AICRM_NEXT_ENV"] = "production"
        os.environ.pop("DATABASE_URL", None)
        os.environ["AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"] = "0"
        os.environ["AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE"] = "1"
        reset_action_template_fixture_state()
        prod_client = TestClient(create_app(), raise_server_exceptions=False)
        prod = prod_client.post(
            "/api/admin/automation-conversion/action-templates",
            json={"template_name": "Prod", "template_code": "prod", "idempotency_key": "prod", "operator": "checker"},
        )
        if prod.status_code != 503:
            blockers.append(f"production fixture POST must be blocked with 503, got {prod.status_code}: {prod.text}")
        else:
            body = prod.json()
            if body.get("error_code") != "production_repository_not_enabled" or body.get("ok") is not False:
                blockers.append("production guard must return production_repository_not_enabled degraded payload")
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings}


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
        blockers.append(f"unexpected changed files outside Phase 4AE scope: {unexpected}")
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_doc_claims() -> dict[str, Any]:
    text = _read(PLAN_MD).lower()
    blockers: list[str] = []
    for pattern in (
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
        "static_code": check_static_code(),
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
        "# Phase 4AE Action Templates Native Fixture Contract Check",
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
    parser = argparse.ArgumentParser(description="Check Phase 4AE action templates native fixture/local contract.")
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
