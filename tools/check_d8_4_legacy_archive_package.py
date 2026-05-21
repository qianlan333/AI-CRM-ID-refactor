#!/usr/bin/env python
from __future__ import annotations

import argparse
import ast
import json
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Json = dict[str, Any]

FORBIDDEN_STATUS_MARKERS = ["delete_ready", "production_ready", "production_approved"]

DOCS_TO_SCAN = [
    "docs/d8_4_legacy_flask_archive_package_implementation.md",
    "docs/d8_4_legacy_flask_archive_package_report.md",
    "docs/d8_legacy_flask_shell_retirement_plan.md",
    "docs/d8_3_legacy_package_move_map.md",
    "docs/d8_3_legacy_import_rewrite_plan.md",
    "docs/legacy_retirement_plan.md",
    "docs/legacy_delete_batches.md",
    "docs/legacy_route_owner_cutover_matrix.md",
    "docs/module_status_matrix.md",
    "docs/remaining_work_queue.md",
    "docs/go_no_go_checklist.md",
]


def _path(relpath: str) -> Path:
    return PROJECT_ROOT / relpath


def _read(relpath: str) -> str:
    return _path(relpath).read_text(encoding="utf-8")


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


def _check_package(blockers: list[Json]) -> Json:
    files = {
        "legacy_flask/__init__.py": _path("legacy_flask/__init__.py").exists(),
        "legacy_flask/app_factory.py": _path("legacy_flask/app_factory.py").exists(),
        "legacy_flask/routes.py": _path("legacy_flask/routes.py").exists(),
        "legacy_flask/http/__init__.py": _path("legacy_flask/http/__init__.py").exists(),
        "legacy_flask/legacy_lockdown.py": _path("legacy_flask/legacy_lockdown.py").exists(),
        "legacy_flask/README.md": _path("legacy_flask/README.md").exists(),
    }
    for relpath, present in files.items():
        if not present:
            blockers.append({"reason": "missing_legacy_flask_package_file", "path": relpath})
    return {"exists": all(files.values()), "files": files}


def _check_shims(blockers: list[Json]) -> Json:
    shim_files = [
        "wecom_ability_service/__init__.py",
        "wecom_ability_service/routes.py",
        "wecom_ability_service/http/__init__.py",
        "wecom_ability_service/legacy_lockdown.py",
    ]
    result: Json = {}
    for relpath in shim_files:
        exists = _path(relpath).exists()
        marked = exists and "LEGACY_COMPATIBILITY_SHIM" in _read(relpath)
        result[relpath] = {"exists": exists, "marked": marked}
        if not exists:
            blockers.append({"reason": "missing_compatibility_shim", "path": relpath})
        elif not marked:
            blockers.append({"reason": "compatibility_shim_marker_missing", "path": relpath})
    return result


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def _check_default_runtime(blockers: list[Json]) -> Json:
    source = _read("app.py") if _path("app.py").exists() else ""
    default_next = 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in source and 'command = args.command or "run"' in source and "run_next()" in source
    top_imports = _top_level_imports(_path("app.py")) if _path("app.py").exists() else set()
    forbidden_top_level = sorted(name for name in ["legacy_flask", "wecom_ability_service"] if name in top_imports)
    if not default_next:
        blockers.append({"reason": "app_py_default_not_next"})
    if forbidden_top_level:
        blockers.append({"reason": "app_py_top_level_legacy_import", "imports": forbidden_top_level})
    return {
        "default_runtime": "ai_crm_next" if default_next else "unknown",
        "top_level_legacy_imports": forbidden_top_level,
    }


def _check_legacy_flask_app(blockers: list[Json]) -> Json:
    source = _read("legacy_flask_app.py") if _path("legacy_flask_app.py").exists() else ""
    imports_archive = "legacy_flask.app_factory import create_app" in source
    mentions_shim = "wecom_ability_service remains a compatibility shim" in source
    if not imports_archive:
        blockers.append({"reason": "legacy_flask_app_not_using_archive_package"})
    return {"imports_legacy_flask": imports_archive, "mentions_shim": mentions_shim}


def _run_python_probe(script: str) -> tuple[bool, Json]:
    completed = subprocess.run(
        ["python3", "-c", script],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        return False, {"stdout": completed.stdout, "stderr": completed.stderr, "returncode": completed.returncode}
    try:
        return True, json.loads(completed.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return False, {"stdout": completed.stdout, "stderr": completed.stderr, "error": f"{type(exc).__name__}: {exc}"}


def _check_legacy_import_and_routes(blockers: list[Json]) -> tuple[Json, Json, Json]:
    import_ok, import_payload = _run_python_probe(
        """
import json
from legacy_flask.app_factory import create_app
from wecom_ability_service import create_app as shim_create_app
print(json.dumps({
    "legacy_flask_create_app": callable(create_app),
    "wecom_ability_service_shim_create_app": callable(shim_create_app),
}, ensure_ascii=False))
"""
    )
    if not import_ok or not import_payload.get("legacy_flask_create_app") or not import_payload.get("wecom_ability_service_shim_create_app"):
        blockers.append({"reason": "legacy_fallback_import_failed", "details": import_payload})

    route_ok, route_payload = _run_python_probe(
        """
import json
from legacy_flask.app_factory import create_app
app = create_app({"TESTING": True, "DATABASE_URL": ""})
client = app.test_client()
retired = client.get("/api/customers")
allowed = client.get("/api/system/health")
print(json.dumps({
    "retired": {
        "status_code": retired.status_code,
        "error": (retired.get_json(silent=True) or {}).get("error"),
        "route_owner": retired.headers.get("X-AICRM-Route-Owner"),
    },
    "allowed": {
        "status_code": allowed.status_code,
        "error": (allowed.get_json(silent=True) or {}).get("error"),
        "route_owner": allowed.headers.get("X-AICRM-Route-Owner"),
    },
}, ensure_ascii=False))
"""
    )
    if not route_ok:
        blockers.append({"reason": "legacy_route_probe_failed", "details": route_payload})
    else:
        retired = route_payload.get("retired", {})
        allowed = route_payload.get("allowed", {})
        if retired.get("status_code") != 410 or retired.get("error") != "legacy_route_retired":
            blockers.append({"reason": "retired_route_not_blocked", "details": retired})
        if allowed.get("status_code") == 410 and allowed.get("error") == "legacy_route_retired":
            blockers.append({"reason": "allowed_fallback_route_blocked", "details": allowed})

    return import_payload, route_payload.get("retired", {}) if route_ok else {}, route_payload.get("allowed", {}) if route_ok else {}


def _check_openclaw(blockers: list[Json]) -> Json:
    exists = _path("openclaw_service").exists()
    if not exists:
        blockers.append({"reason": "openclaw_service_missing"})
    return {"exists": exists, "status": "retained" if exists else "missing"}


def _check_production_config_modified(blockers: list[Json]) -> Json:
    modified = [path for path in _changed_paths() if _is_production_config_path(path)]
    if modified:
        blockers.append({"reason": "production_config_modified", "paths": modified})
    return {"production_config_modified": bool(modified), "modified_paths": modified}


def _check_forbidden_status_markers(blockers: list[Json]) -> list[Json]:
    findings: list[Json] = []
    for relpath in DOCS_TO_SCAN:
        path = _path(relpath)
        if not path.exists():
            blockers.append({"reason": "missing_doc_for_status_scan", "path": relpath})
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_STATUS_MARKERS:
            if marker in text:
                finding = {"path": relpath, "marker": marker}
                findings.append(finding)
                blockers.append({"reason": "forbidden_status_marker", **finding})
    return findings


def run_check() -> Json:
    blockers: list[Json] = []
    warnings: list[Json] = []
    package = _check_package(blockers)
    shims = _check_shims(blockers)
    default_runtime = _check_default_runtime(blockers)
    legacy_flask_app = _check_legacy_flask_app(blockers)
    legacy_import, lockdown_status, allowed_fallback_status = _check_legacy_import_and_routes(blockers)
    openclaw = _check_openclaw(blockers)
    production_config = _check_production_config_modified(blockers)
    forbidden_status_markers = _check_forbidden_status_markers(blockers)
    if not blockers:
        warnings.append(
            {
                "reason": "archive_entry_layer_only",
                "message": "D8.4 archives the legacy shell entry layer; domains/templates/static remain in the old package for compatibility.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "legacy_flask_package_exists": package["exists"],
        "package_files": package["files"],
        "compatibility_shims": shims,
        "default_runtime": default_runtime,
        "legacy_flask_app": legacy_flask_app,
        "legacy_fallback_import": legacy_import,
        "lockdown_status": lockdown_status,
        "allowed_fallback_status": allowed_fallback_status,
        "openclaw_service_status": openclaw,
        "production_config_modified": production_config["production_config_modified"],
        "production_config": production_config,
        "forbidden_status_markers": forbidden_status_markers,
        "recommendation": (
            "READY_FOR_D8_4_ARCHIVE_PACKAGE_ACCEPTANCE"
            if not blockers
            else "FIX_D8_4_ARCHIVE_PACKAGE_BLOCKERS_BEFORE_ACCEPTANCE"
        ),
    }


def _write_markdown(path: str, result: Json) -> None:
    lines = [
        "# D8.4 Legacy Archive Package Check",
        "",
        f"- ok: `{str(result['ok']).lower()}`",
        f"- blockers: `{len(result['blockers'])}`",
        f"- warnings: `{len(result['warnings'])}`",
        f"- legacy_flask_package_exists: `{str(result['legacy_flask_package_exists']).lower()}`",
        f"- default_runtime: `{result['default_runtime'].get('default_runtime')}`",
        f"- legacy_fallback_import: `{result['legacy_fallback_import']}`",
        f"- openclaw_service_status: `{result['openclaw_service_status']}`",
        f"- production_config_modified: `{str(result['production_config_modified']).lower()}`",
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
    parser = argparse.ArgumentParser(description="Check D8.4 legacy archive package implementation.")
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
