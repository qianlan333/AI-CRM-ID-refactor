#!/usr/bin/env python
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

Json = dict[str, Any]

FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]

DOCS_TO_SCAN = [
    "docs/d8_2_legacy_fallback_route_lockdown_enforcement.md",
    "docs/d8_2_legacy_fallback_route_lockdown_report.md",
    "docs/d8_legacy_flask_shell_retirement_plan.md",
    "docs/d8_1_legacy_fallback_route_lockdown_plan.md",
    "docs/d8_1_legacy_fallback_route_matrix.md",
    "docs/legacy_retirement_plan.md",
    "docs/legacy_delete_batches.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]

RETIRED_SMOKE_ROUTES = [
    ("GET", "/api/customers"),
    ("GET", "/admin/customers"),
    ("GET", "/api/admin/user-ops/overview"),
    ("GET", "/admin/questionnaires"),
    ("GET", "/api/admin/automation-conversion/overview"),
]

ALLOWED_SMOKE_ROUTES = [
    ("GET", "/api/system/health"),
]


def _path(relpath: str) -> Path:
    return PROJECT_ROOT / relpath


def _read(relpath: str) -> str:
    return _path(relpath).read_text(encoding="utf-8")


def _load_legacy_lockdown_module():
    module_path = _path("wecom_ability_service/legacy_lockdown.py")
    spec = importlib.util.spec_from_file_location("d8_legacy_lockdown_contract", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _changed_paths() -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    paths: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        paths.append(path)
    return paths


def _is_production_config_path(path: str) -> bool:
    lowered = path.lower()
    return (
        lowered.startswith("deploy/")
        or lowered == ".github/workflows/deploy.yml"
        or "nginx" in lowered
        or "systemd" in lowered
        or lowered.endswith(".service")
        or lowered.endswith(".timer")
    )


def _check_production_config_modified(blockers: list[Json]) -> Json:
    modified = [path for path in _changed_paths() if _is_production_config_path(path)]
    if modified:
        blockers.append({"reason": "production_config_modified", "paths": modified})
    return {"production_config_modified": bool(modified), "modified_paths": modified}


def _check_docs(blockers: list[Json]) -> list[Json]:
    findings: list[Json] = []
    for relpath in DOCS_TO_SCAN:
        path = _path(relpath)
        if not path.exists():
            blockers.append({"reason": "missing_doc", "path": relpath})
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_STATUS_MARKERS:
            if marker in text:
                item = {"path": relpath, "marker": marker}
                findings.append(item)
                blockers.append({"reason": "forbidden_status_marker", **item})
    return findings


def _check_module_contract(blockers: list[Json]) -> Json:
    if not _path("wecom_ability_service/legacy_lockdown.py").exists():
        blockers.append({"reason": "missing_legacy_lockdown_module"})
        return {"module_exists": False}
    legacy_lockdown = _load_legacy_lockdown_module()

    retired_rules, allowed_rules = legacy_lockdown.load_lockdown_rules()
    checks = {
        "module_exists": True,
        "register_legacy_lockdown_exists": callable(getattr(legacy_lockdown, "register_legacy_lockdown", None)),
        "retired_rule_count": len(retired_rules),
        "allowed_rule_count": len(allowed_rules),
        "d1_d6_groups": {
            "media": any(rule.category == "media_readonly" for rule in retired_rules),
            "product": any(rule.category == "product_readonly" for rule in retired_rules),
            "customer": any(rule.category == "customer_readonly" for rule in retired_rules),
            "user_ops": any(rule.category == "user_ops_readonly" for rule in retired_rules),
            "questionnaire": any(rule.category == "questionnaire_readonly" for rule in retired_rules),
            "automation": any(rule.category == "automation_readonly" for rule in retired_rules),
        },
        "allowed_examples": {
            "payment": legacy_lockdown.match_allowed_fallback_route("GET", "/p/sample")[0],
            "questionnaire_submit": legacy_lockdown.match_allowed_fallback_route("POST", "/api/h5/questionnaires/demo/submit")[0],
            "oauth": legacy_lockdown.match_allowed_fallback_route("GET", "/api/h5/wechat/oauth/start")[0],
            "archive": legacy_lockdown.match_allowed_fallback_route("POST", "/api/archive/sync")[0],
            "openclaw": legacy_lockdown.match_allowed_fallback_route("POST", "/api/admin/automation-conversion/member/push-openclaw")[0],
            "diagnostic": legacy_lockdown.match_allowed_fallback_route("GET", "/api/system/health")[0],
        },
        "retired_examples": {
            "customer": legacy_lockdown.match_retired_route("GET", "/api/customers")[0],
            "user_ops": legacy_lockdown.match_retired_route("GET", "/api/admin/user-ops/overview")[0],
            "questionnaire": legacy_lockdown.match_retired_route("GET", "/admin/questionnaires")[0],
            "automation": legacy_lockdown.match_retired_route("GET", "/api/admin/automation-conversion/overview")[0],
        },
    }
    if not checks["register_legacy_lockdown_exists"]:
        blockers.append({"reason": "missing_register_legacy_lockdown"})
    for group, present in checks["d1_d6_groups"].items():
        if not present:
            blockers.append({"reason": "missing_retired_rule_group", "group": group})
    for name, present in checks["allowed_examples"].items():
        if not present:
            blockers.append({"reason": "missing_allowed_fallback_rule", "example": name})
    for name, present in checks["retired_examples"].items():
        if not present:
            blockers.append({"reason": "missing_retired_route_rule", "example": name})
    return checks


def _check_app_factory_registration(blockers: list[Json]) -> bool:
    legacy_flask_source = (
        _read("legacy_flask/app_factory.py") if _path("legacy_flask/app_factory.py").exists() else ""
    )
    shim_source = _read("wecom_ability_service/__init__.py") if _path("wecom_ability_service/__init__.py").exists() else ""
    registered = (
        "register_legacy_lockdown(app)" in legacy_flask_source
        and "from legacy_flask.legacy_lockdown import register_legacy_lockdown" in legacy_flask_source
        and "LEGACY_COMPATIBILITY_SHIM" in shim_source
    )
    if not registered:
        blockers.append({"reason": "lockdown_not_registered_in_legacy_app_factory"})
    return registered


def _check_default_runtime(blockers: list[Json]) -> Json:
    source = _read("app.py") if _path("app.py").exists() else ""
    default_next = 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in source and 'command = args.command or "run"' in source and "run_next()" in source
    if not default_next:
        blockers.append({"reason": "app_py_default_not_next"})
    return {"default_runtime": "ai_crm_next" if default_next else "unknown"}


def _check_legacy_presence(blockers: list[Json]) -> Json:
    exists = {
        "legacy_flask_app.py": _path("legacy_flask_app.py").exists(),
        "wecom_ability_service": _path("wecom_ability_service").exists(),
        "wecom_ability_service/http/__init__.py": _path("wecom_ability_service/http/__init__.py").exists(),
        "openclaw_service": _path("openclaw_service").exists(),
    }
    for path, present in exists.items():
        if not present:
            blockers.append({"reason": "missing_legacy_component", "path": path})
    return exists


def _check_flask_runtime(blockers: list[Json]) -> tuple[list[Json], list[Json]]:
    script = """
import json
from wecom_ability_service import create_app

retired_routes = [
    ("GET", "/api/customers"),
    ("GET", "/admin/customers"),
    ("GET", "/api/admin/user-ops/overview"),
    ("GET", "/admin/questionnaires"),
    ("GET", "/api/admin/automation-conversion/overview"),
]
allowed_routes = [("GET", "/api/system/health")]

app = create_app({"TESTING": True, "DATABASE_URL": ""})
client = app.test_client()
retired_results = []
for method, path in retired_routes:
    response = client.open(path, method=method)
    payload = response.get_json(silent=True) or {}
    retired_results.append(
        {
            "method": method,
            "path": path,
            "status_code": response.status_code,
            "error": payload.get("error"),
            "route_owner": response.headers.get("X-AICRM-Route-Owner"),
            "next_owner": response.headers.get("X-AICRM-Next-Owner"),
        }
    )
allowed_results = []
for method, path in allowed_routes:
    response = client.open(path, method=method)
    payload = response.get_json(silent=True) or {}
    allowed_results.append(
        {
            "method": method,
            "path": path,
            "status_code": response.status_code,
            "error": payload.get("error"),
            "route_owner": response.headers.get("X-AICRM-Route-Owner"),
        }
    )
print(json.dumps({"retired": retired_results, "allowed": allowed_results}, ensure_ascii=False))
"""
    completed = subprocess.run(
        ["python3", "-c", script],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        blockers.append(
            {
                "reason": "legacy_app_factory_failed",
                "error": completed.stderr.strip() or completed.stdout.strip(),
            }
        )
        return [], []
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        blockers.append({"reason": "legacy_runtime_probe_invalid_json", "error": str(exc), "stdout": completed.stdout})
        return [], []
    retired_results = payload.get("retired", [])
    allowed_results = payload.get("allowed", [])
    for item in retired_results:
        if item.get("status_code") != 410 or item.get("error") != "legacy_route_retired":
            blockers.append({"reason": "retired_route_not_blocked", **item})
    for item in allowed_results:
        if item.get("status_code") == 410 and item.get("error") == "legacy_route_retired":
            blockers.append({"reason": "allowed_fallback_route_blocked", **item})
    return retired_results, allowed_results


def run_check() -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    module_contract = _check_module_contract(blockers)
    lockdown_registered = _check_app_factory_registration(blockers)
    default_runtime = _check_default_runtime(blockers)
    legacy_presence = _check_legacy_presence(blockers)
    retired_results, allowed_results = _check_flask_runtime(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_status_markers = _check_docs(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "legacy_fallback_only",
                "message": "D8.2 enforcement is registered only in legacy Flask fallback; app.py default remains AI-CRM Next.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "retired_routes_checked": retired_results,
        "retired_routes_blocked": [
            item for item in retired_results if item["status_code"] == 410 and item["error"] == "legacy_route_retired"
        ],
        "allowed_fallback_routes_checked": allowed_results,
        "allowed_fallback_routes_blocked": [
            item for item in allowed_results if item["status_code"] == 410 and item["error"] == "legacy_route_retired"
        ],
        "lockdown_registered": lockdown_registered,
        "legacy_fallback_exists": all(legacy_presence.values()),
        "legacy_presence": legacy_presence,
        "default_runtime": default_runtime,
        "module_contract": module_contract,
        "production_config_modified": production_config["production_config_modified"],
        "production_config": production_config,
        "forbidden_status_markers": forbidden_status_markers,
        "recommendation": (
            "READY_FOR_D8_2_LOCKDOWN_ENFORCEMENT_ACCEPTANCE"
            if not blockers
            else "FIX_D8_2_LOCKDOWN_ENFORCEMENT_BLOCKERS_BEFORE_ACCEPTANCE"
        ),
    }


def _write_markdown(path: str, result: Json) -> None:
    lines = [
        "# D8.2 Legacy Lockdown Enforcement Check",
        "",
        f"- ok: `{str(result['ok']).lower()}`",
        f"- blockers: `{len(result['blockers'])}`",
        f"- warnings: `{len(result['warnings'])}`",
        f"- lockdown_registered: `{str(result['lockdown_registered']).lower()}`",
        f"- legacy_fallback_exists: `{str(result['legacy_fallback_exists']).lower()}`",
        f"- retired routes checked: `{len(result['retired_routes_checked'])}`",
        f"- retired routes blocked: `{len(result['retired_routes_blocked'])}`",
        f"- allowed fallback routes checked: `{len(result['allowed_fallback_routes_checked'])}`",
        f"- allowed fallback routes blocked: `{len(result['allowed_fallback_routes_blocked'])}`",
        f"- production config modified: `{str(result['production_config_modified']).lower()}`",
        f"- recommendation: `{result['recommendation']}`",
        "",
        "## Blockers",
    ]
    if result["blockers"]:
        lines.extend(f"- `{item}`" for item in result["blockers"])
    else:
        lines.append("- none")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check D8.2 legacy fallback route lockdown enforcement.")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    result = run_check()
    if args.output_md:
        _write_markdown(args.output_md, result)
        print(f"wrote markdown report: {args.output_md}")
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote json report: {args.output_json}")
    print(f"overall: {'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
