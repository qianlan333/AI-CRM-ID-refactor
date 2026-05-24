#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4c_profile_segment_template_native_contract.md"
PHASE4B_CHECKER = ROOT / "tools/check_phase4b_profile_segment_template_plan.py"
MAIN = ROOT / "aicrm_next/main.py"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"
AUTOMATION_API = ROOT / "aicrm_next/automation_engine/api.py"
AUTOMATION_APP = ROOT / "aicrm_next/automation_engine/application.py"
AUTOMATION_REPO = ROOT / "aicrm_next/automation_engine/repo.py"
PROFILE_SEGMENTS = ROOT / "aicrm_next/automation_engine/profile_segments.py"
EXPECTED_MODULE = "aicrm_next.automation_engine.api"
EXPECTED_ROUTES = {
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/catalog"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/options"),
    ("GET", "/api/admin/automation-conversion/profile-segment-templates/{template_id}"),
    ("POST", "/api/admin/automation-conversion/profile-segment-templates"),
    ("PUT", "/api/admin/automation-conversion/profile-segment-templates/{template_id}"),
}
WRITE_ROUTES = {
    ("POST", "/api/admin/automation-conversion/profile-segment-templates"),
    ("PUT", "/api/admin/automation-conversion/profile-segment-templates/{template_id}"),
}
ALLOWED_CHANGED_FILES = {
    "aicrm_next/automation_engine/api.py",
    "aicrm_next/automation_engine/application.py",
    "aicrm_next/automation_engine/domain.py",
    "aicrm_next/automation_engine/dto.py",
    "aicrm_next/automation_engine/repo.py",
    "aicrm_next/automation_engine/profile_segments.py",
    "docs/development/phase_4c_profile_segment_template_native_contract.md",
    "docs/development/phase_4d_profile_segment_template_production_switch_plan.md",
    "docs/development/phase_4d_profile_segment_template_production_switch_plan.yaml",
    "docs/development/phase_4e_profile_segment_template_repository_adapter_plan.md",
    "docs/development/phase_4e_profile_segment_template_repository_adapter_plan.yaml",
    "tools/check_phase4a_internal_write_candidate_selection.py",
    "tools/check_phase4b_profile_segment_template_plan.py",
    "tools/check_phase4c_profile_segment_template_native_contract.py",
    "tools/check_phase4d_profile_segment_template_production_switch_plan.py",
    "tools/check_phase4e_profile_segment_template_repository_adapter_plan.py",
    "tests/test_phase4c_profile_segment_template_native_contract.py",
    "tests/test_phase4d_profile_segment_template_production_switch_plan.py",
    "tests/test_phase4e_profile_segment_template_repository_adapter_plan.py",
}
PROTECTED_DISALLOWED_PREFIXES = (
    "wecom_ability_service/",
    "migrations/",
    "deploy",
    "systemd",
    "nginx",
)
PROTECTED_DISALLOWED_EXACT = {
    "aicrm_next/main.py",
    "aicrm_next/production_compat/api.py",
    "app.py",
    "legacy_flask_app.py",
}
DANGEROUS_FIELDS = (
    "run_due",
    "execution",
    "send",
    "wecom",
    "openclaw",
    "mcp",
    "timer",
    "workflow_activation",
    "customer_pool_state_change",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run(command: list[str], *, env: dict[str, str] | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def _changed_files_from_git() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    commands = [
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    for command in commands:
        code, output = _run(command)
        if code == 0:
            changed.update(line.strip() for line in output.splitlines() if line.strip())
        else:
            warnings.append(f"{' '.join(command)} unavailable: {output}")
    return changed, warnings


@contextmanager
def _patched_env(values: dict[str, str | None]):
    old = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _route_path(path: str) -> str:
    return path.replace("/{path:path}", "/*")


def _registered_routes(app: Any) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for route in getattr(app, "routes", []):
        methods = sorted(getattr(route, "methods", set()) or [])
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        module = getattr(endpoint, "__module__", "")
        for method in methods:
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                result[(method, path)] = module
    return result


def _json_body(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return getattr(response, "text", "")


def _body_has_fixture_success(body: Any) -> bool:
    text = json.dumps(body, ensure_ascii=False, sort_keys=True).lower() if not isinstance(body, str) else body.lower()
    markers = ("fixture", "local_contract", "demo")
    success_markers = ('"ok": true', "'ok': true", "ok true")
    return any(marker in text for marker in markers) and any(marker in text for marker in success_markers)


def _all_side_effect_flags_false(body: dict[str, Any]) -> bool:
    safety = body.get("side_effect_safety")
    if not isinstance(safety, dict):
        return False
    return all(value is False for key, value in safety.items() if key.startswith("real_"))


def _find_route_decorators() -> dict[tuple[str, str], str]:
    tree = ast.parse(_read(AUTOMATION_API))
    found: dict[tuple[str, str], str] = {}
    method_by_attr = {
        "get": "GET",
        "post": "POST",
        "put": "PUT",
        "patch": "PATCH",
        "delete": "DELETE",
    }
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            method = method_by_attr.get(decorator.func.attr)
            if not method or not decorator.args:
                continue
            arg = decorator.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found[(method, arg.value)] = node.name
    return found


def _function_body_text(function_name: str) -> str:
    text = _read(AUTOMATION_API)
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    return ""


def check_required_docs() -> dict[str, Any]:
    required = [
        DOC,
        ROOT / "docs/development/phase_4b_profile_segment_template_implementation_plan.md",
        ROOT / "docs/development/phase_4b_profile_segment_template_implementation_plan.yaml",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    return {"ok": not missing, "blockers": [f"missing required doc: {path}" for path in missing], "warnings": []}


def check_static_routes() -> dict[str, Any]:
    blockers: list[str] = []
    routes = _find_route_decorators()
    missing = sorted(EXPECTED_ROUTES - set(routes))
    if missing:
        blockers.append(f"missing Next profile-segment-template routes: {missing}")
    delete_routes = sorted((method, path) for method, path in routes if method == "DELETE" and "profile-segment-templates" in path)
    if delete_routes:
        blockers.append(f"DELETE profile-segment-template route is not allowed in Phase 4C: {delete_routes}")
    api_text = _read(AUTOMATION_API)
    if "wecom_ability_service" in api_text:
        blockers.append("automation_engine/api.py must not directly import wecom_ability_service")
    if "forward_to_legacy_flask" in api_text:
        blockers.append("automation_engine/api.py must not call route-level legacy forward")
    for (_method, _path), function_name in routes.items():
        if "profile_segment_template" not in function_name:
            continue
        body = _function_body_text(function_name)
        for token in ("wecom_ability_service", "forward_to_legacy_flask", "run_due", "workflow_activation"):
            if token in body:
                blockers.append(f"{function_name} contains forbidden token {token}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_static_contract_code() -> dict[str, Any]:
    blockers: list[str] = []
    profile_text = _read(PROFILE_SEGMENTS)
    app_text = _read(AUTOMATION_APP)
    repo_text = _read(AUTOMATION_REPO)
    for token in DANGEROUS_FIELDS:
        if token not in profile_text:
            blockers.append(f"profile segment validator does not mention dangerous field: {token}")
    for token in ("idempotency_key is required", "production_unavailable", "side_effect_safety"):
        if token not in app_text:
            blockers.append(f"application contract missing {token}")
    for token in ("_profile_segment_idempotency", "audit_event", "rollback"):
        if token not in repo_text:
            blockers.append(f"repository contract missing {token}")
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_phase4b_plan() -> dict[str, Any]:
    code, output = _run(["python3", str(PHASE4B_CHECKER), "--output-json", "/tmp/phase4b_profile_segment_template_plan_from_phase4c.json"])
    blockers = [] if code == 0 else [f"Phase 4B checker failed: {output}"]
    return {"ok": not blockers, "blockers": blockers, "warnings": []}


def check_no_forbidden_file_changes() -> dict[str, Any]:
    changed, warnings = _changed_files_from_git()
    blockers: list[str] = []
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files outside Phase 4C scope: {unexpected}")
    forbidden = sorted(
        path
        for path in changed
        if path in PROTECTED_DISALLOWED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_DISALLOWED_PREFIXES)
    )
    if forbidden:
        blockers.append(f"forbidden runtime/protected files changed: {forbidden}")
    schema = sorted(path for path in changed if "schema" in path.lower() or "migration" in path.lower())
    schema = [path for path in schema if path not in ALLOWED_CHANGED_FILES]
    if schema:
        blockers.append(f"schema/migration-like files changed: {schema}")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "changed_files": sorted(changed)}


def check_fastapi_route_behavior() -> dict[str, Any]:
    try:
        import fastapi  # noqa: F401
        from fastapi.testclient import TestClient
    except ModuleNotFoundError as exc:
        if exc.name == "fastapi":
            return {
                "ok": True,
                "blockers": [],
                "warnings": ["FastAPI is not installed; skipped TestClient route probes in bare python."],
                "skipped": True,
            }
        raise

    blockers: list[str] = []
    warnings: list[str] = []
    fixture_env = {
        "AICRM_NEXT_ENV": "test",
        "DATABASE_URL": None,
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": "0",
    }
    with _patched_env(fixture_env):
        from aicrm_next.main import create_app

        app = create_app()
        routes = _registered_routes(app)
        for route in EXPECTED_ROUTES:
            module = routes.get(route)
            if module != EXPECTED_MODULE:
                blockers.append(f"{route} endpoint module expected {EXPECTED_MODULE}, got {module}")
        client = TestClient(app, raise_server_exceptions=False)
        for path in (
            "/api/admin/automation-conversion/profile-segment-templates/catalog",
            "/api/admin/automation-conversion/profile-segment-templates",
            "/api/admin/automation-conversion/profile-segment-templates/options",
            "/api/admin/automation-conversion/profile-segment-templates/1",
        ):
            response = client.get(path)
            body = _json_body(response)
            if response.headers.get("X-AICRM-Route-Owner") != "ai_crm_next":
                blockers.append(f"{path} missing ai_crm_next route owner header")
            if response.headers.get("X-AICRM-Compatibility-Facade") == "legacy_flask_facade":
                blockers.append(f"{path} unexpectedly used legacy compatibility facade")
            if response.status_code != 200:
                blockers.append(f"{path} expected 200 in fixture mode, got {response.status_code}: {body}")
            if isinstance(body, dict) and not _all_side_effect_flags_false(body):
                blockers.append(f"{path} missing false side_effect_safety flags")
        create_response = client.post(
            "/api/admin/automation-conversion/profile-segment-templates",
            json={"name": "Phase 4C probe", "code": "phase4c_probe", "idempotency_key": "phase4c-probe", "operator": "checker"},
        )
        if create_response.status_code not in {200, 201}:
            blockers.append(f"create expected 2xx in fixture mode, got {create_response.status_code}: {_json_body(create_response)}")
        create_body = _json_body(create_response)
        if isinstance(create_body, dict) and not _all_side_effect_flags_false(create_body):
            blockers.append("create missing false side_effect_safety flags")
        update_response = client.put(
            "/api/admin/automation-conversion/profile-segment-templates/2",
            json={"description": "updated by checker", "operator": "checker"},
        )
        if update_response.status_code != 200:
            blockers.append(f"update expected 200 in fixture mode, got {update_response.status_code}: {_json_body(update_response)}")

    prod_env = {
        "AICRM_NEXT_ENV": "production",
        "DATABASE_URL": "postgresql://phase4c:phase4c@127.0.0.1:1/aicrm_phase4c_probe",
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": "1",
    }
    with _patched_env(prod_env):
        from aicrm_next.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/admin/automation-conversion/profile-segment-templates",
            json={"name": "Production probe", "code": "production_probe", "idempotency_key": "prod-probe", "operator": "checker"},
        )
        body = _json_body(response)
        if response.status_code == 200 and _body_has_fixture_success(body):
            blockers.append("production probe returned 200 fixture/local_contract/demo write success")
        if response.status_code in {200, 201} and response.headers.get("X-AICRM-Compatibility-Facade") != "legacy_flask_facade":
            if isinstance(body, dict) and body.get("source_status") != "production_unavailable":
                blockers.append(f"production probe unexpectedly returned Next success: {body}")
        if response.status_code >= 500:
            warnings.append(f"production facade probe returned {response.status_code}; acceptable only if legacy test facade cannot initialize locally")
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings}


def build_report() -> dict[str, Any]:
    checks = {
        "required_docs": check_required_docs(),
        "static_routes": check_static_routes(),
        "static_contract_code": check_static_contract_code(),
        "phase4b_plan": check_phase4b_plan(),
        "no_forbidden_file_changes": check_no_forbidden_file_changes(),
        "fastapi_route_behavior": check_fastapi_route_behavior(),
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
        "# Phase 4C Profile Segment Template Native Contract Check",
        "",
        f"- overall: {report['overall']}",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers") or []
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Warnings"])
    warnings = report.get("warnings") or []
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- none")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Phase 4C profile segment template native contract guardrails.")
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
