from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RETIRED_READONLY_ROUTES: dict[str, set[str]] = {
    "/admin/questionnaires": {"GET"},
    "/admin/questionnaires/ui": {"GET"},
    "/admin/questionnaires/new": {"GET"},
    "/admin/questionnaires/<int:questionnaire_id>": {"GET"},
    "/api/admin/questionnaires": {"GET"},
    "/api/admin/questionnaires/preflight": {"GET"},
    "/api/admin/questionnaires/<int:questionnaire_id>": {"GET"},
    "/api/admin/questionnaires/<int:questionnaire_id>/latest-submit-debug": {"GET"},
    "/api/admin/questionnaires/<int:questionnaire_id>/export": {"GET"},
    "/s/<slug>": {"GET"},
    "/s/<slug>/submitted": {"GET"},
    "/s/<slug>/result/<result_token>": {"GET"},
    "/api/h5/questionnaires/<slug>": {"GET"},
}

RETAINED_FALLBACK_ROUTES: dict[str, set[str]] = {
    "/api/admin/questionnaires": {"POST"},
    "/api/admin/questionnaires/<int:questionnaire_id>": {"PUT", "DELETE"},
    "/api/admin/questionnaires/<int:questionnaire_id>/disable": {"POST"},
    "/api/h5/questionnaires/<slug>/submit": {"POST"},
    "/api/h5/wechat/oauth/start": {"GET"},
    "/api/h5/wechat/oauth/callback": {"GET"},
    "/api/h5/questionnaires/<slug>/client-diagnostics": {"POST"},
    "/api/debug/questionnaire/session": {"GET"},
    "/admin/questionnaires/<int:questionnaire_id>/save": {"POST"},
    "/admin/questionnaires/<int:questionnaire_id>/toggle": {"POST"},
    "/admin/questionnaires/external-push-logs": {"GET"},
    "/admin/questionnaires/external-push-logs/retry-batch": {"POST"},
    "/admin/questionnaires/external-push-logs/<int:push_log_id>/retry": {"POST"},
    "/admin/questionnaires/<int:questionnaire_id>/external-push-logs": {"GET"},
    "/admin/questionnaires/<int:questionnaire_id>/external-push-logs/<int:push_log_id>/retry": {"POST"},
    "/admin/questionnaires/<int:questionnaire_id>/external-push-logs/retry-batch": {"POST"},
}

RETAINED_FALLBACK_FILES = [
    "wecom_ability_service/http/admin_questionnaires.py",
    "wecom_ability_service/http/admin_questionnaire_console.py",
    "wecom_ability_service/http/public_questionnaires.py",
    "wecom_ability_service/http/public_questionnaire_oauth.py",
    "wecom_ability_service/http/public_questionnaire_diagnostics.py",
    "wecom_ability_service/http/admin_questionnaire_push_logs.py",
    "wecom_ability_service/http/questionnaire_support.py",
    "wecom_ability_service/domains/questionnaire/service.py",
]

NEXT_QUESTIONNAIRE_ROUTE_TOKENS = [
    '@router.get("/api/admin/questionnaires")',
    '@router.get("/api/admin/questionnaires/preflight")',
    '@router.get("/api/admin/questionnaires/{questionnaire_id}")',
    '@router.get("/api/admin/questionnaires/{questionnaire_id}/export")',
    '@router.get("/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug")',
    '@router.get("/api/h5/questionnaires/{slug}")',
    '@router.get("/api/h5/questionnaires/{slug}/result/{submission_id}")',
    '@router.get("/s/{slug}"',
]

PRODUCTION_CONFIG_PREFIXES = ("deploy/", ".github/")
PRODUCTION_CONFIG_KEYWORDS = ("nginx", "production", "systemd", "supervisor", "docker-compose")


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _git_changed_files() -> list[str]:
    changed: set[str] = set()
    for command in (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            result = subprocess.run(command, cwd=REPO_ROOT, check=True, capture_output=True, text=True)
        except Exception:
            continue
        changed.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(changed)


def _production_config_modified(changed_files: list[str]) -> bool:
    for path in changed_files:
        lower = path.lower()
        if lower.startswith(PRODUCTION_CONFIG_PREFIXES):
            return True
        if any(keyword in lower for keyword in PRODUCTION_CONFIG_KEYWORDS):
            if lower.startswith(("docs/", "tests/", "tools/")):
                continue
            return True
    return False


def _legacy_route_methods() -> dict[str, set[str]]:
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    routes: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        methods = set(rule.methods) - {"HEAD", "OPTIONS"}
        routes.setdefault(rule.rule, set()).update(methods)
    return routes


def _source_route_lines(path: str) -> list[str]:
    lines = []
    for line in _read(path).splitlines():
        stripped = line.strip()
        if "bp.route(" in stripped:
            lines.append(stripped)
    return lines


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    try:
        legacy_routes = _legacy_route_methods()
        legacy_import_failed = False
    except Exception as exc:
        legacy_routes = {}
        legacy_import_failed = True
        blockers.append(f"legacy Flask fallback create_app import failed: {exc}")

    retired_readonly_routes: dict[str, bool] = {}
    stale_readonly_routes: list[str] = []
    if not legacy_import_failed:
        for route, methods in RETIRED_READONLY_ROUTES.items():
            stale_methods = sorted(methods & legacy_routes.get(route, set()))
            retired_readonly_routes[route] = not stale_methods
            if stale_methods:
                stale_readonly_routes.append(f"{','.join(stale_methods)} {route}")
        if stale_readonly_routes:
            blockers.append("legacy Questionnaire readonly routes are still registered")

    retained_write_external_fallbacks = {
        route: sorted(methods) == sorted(methods & legacy_routes.get(route, set()))
        for route, methods in RETAINED_FALLBACK_ROUTES.items()
    }
    if not all(retained_write_external_fallbacks.values()):
        blockers.append("legacy Questionnaire write/submit/OAuth/external fallback route was removed")

    retained_fallback_files = {path: (REPO_ROOT / path).exists() for path in RETAINED_FALLBACK_FILES}
    if not all(retained_fallback_files.values()):
        blockers.append("legacy Questionnaire fallback file was removed")

    source_route_lines = {
        "admin_questionnaires.py": _source_route_lines("wecom_ability_service/http/admin_questionnaires.py"),
        "admin_questionnaire_console.py": _source_route_lines("wecom_ability_service/http/admin_questionnaire_console.py"),
        "public_questionnaires.py": _source_route_lines("wecom_ability_service/http/public_questionnaires.py"),
    }
    for file_name, lines in source_route_lines.items():
        stale_lines = [line for line in lines if "methods=['GET']" in line or 'methods=["GET"]' in line]
        if stale_lines:
            blockers.append(f"{file_name} still registers legacy readonly GET routes")

    questionnaire_api = _read("aicrm_next/questionnaire/api.py")
    frontend_routes = _read("aicrm_next/frontend_compat/legacy_routes.py")
    next_questionnaire_routes = {
        "api": all(token in questionnaire_api for token in NEXT_QUESTIONNAIRE_ROUTE_TOKENS),
        "admin_pages": '"/admin/questionnaires"' in frontend_routes and '"/admin/questionnaires/ui"' in frontend_routes,
        "routes": [
            "GET /admin/questionnaires",
            "GET /admin/questionnaires/ui",
            "GET /api/admin/questionnaires",
            "GET /api/admin/questionnaires/{questionnaire_id}",
            "GET /api/h5/questionnaires/{slug}",
            "GET /api/h5/questionnaires/{slug}/result/{submission_id}",
            "GET /s/{slug}",
        ],
    }
    if not next_questionnaire_routes["api"] or not next_questionnaire_routes["admin_pages"]:
        blockers.append("AI-CRM Next Questionnaire readonly routes are incomplete")

    app_py = _read("app.py")
    default_next = 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in app_py and "uvicorn.run(NEXT_APP_IMPORT" in app_py
    legacy_fallback_exists = (REPO_ROOT / "legacy_flask_app.py").exists()
    if not default_next:
        blockers.append("app.py default runtime is not AI-CRM Next")
    if not legacy_fallback_exists:
        blockers.append("legacy_flask_app.py missing")

    changed_files = _git_changed_files()
    production_config_modified = _production_config_modified(changed_files)
    if production_config_modified:
        blockers.append("production/deploy config modified")

    docs = _read("docs/legacy_delete_batches.md")
    if "D5: Questionnaire Old Readonly Routes" not in docs or "Status: retired/tombstoned" not in docs:
        warnings.append("D5 retired/tombstoned status not explicit in docs/legacy_delete_batches.md")
    for batch in ["D7", "D8", "D9"]:
        marker = f"## {batch}:"
        section = docs.split(marker, 1)[1] if marker in docs else ""
        status_line = next((line.strip().lower() for line in section.splitlines() if line.strip().lower().startswith("status:")), "")
        if status_line.startswith("status: retired") or status_line.startswith("status: deleted"):
            blockers.append(f"{batch} is incorrectly marked retired/deleted")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "retired_readonly_routes": retired_readonly_routes,
        "retained_write_external_fallbacks": retained_write_external_fallbacks,
        "retained_fallback_files": retained_fallback_files,
        "stale_readonly_routes": stale_readonly_routes,
        "source_route_lines": source_route_lines,
        "next_questionnaire_routes": next_questionnaire_routes,
        "legacy_fallback_status": {
            "app_py_default_next": default_next,
            "legacy_flask_app_exists": legacy_fallback_exists,
            "legacy_create_app_import_failed": legacy_import_failed,
        },
        "production_config_modified": production_config_modified,
        "changed_files": changed_files,
        "recommendation": "READY_FOR_D5_QUESTIONNAIRE_RETIREMENT_ACCEPTANCE" if not blockers else "FIX_BLOCKERS",
    }


def _write_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# Legacy D5 Questionnaire Retirement Check",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- production_config_modified: `{str(report['production_config_modified']).lower()}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Stale Readonly Routes", ""])
    lines.extend([f"- `{item}`" for item in report["stale_readonly_routes"]] or ["- none"])
    lines.extend(["", "## Retained Fallback Routes", ""])
    lines.extend([f"- `{route}`: `{str(ok).lower()}`" for route, ok in report["retained_write_external_fallbacks"].items()])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check D5 legacy Questionnaire readonly route retirement.")
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    report = build_report()
    Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(report, Path(args.output_md))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
