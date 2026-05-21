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

RETIRED_ROUTE_OWNER_FILES = [
    "wecom_ability_service/http/admin_user_ops.py",
    "wecom_ability_service/http/admin_user_ops_delivery.py",
]

WRITE_FALLBACK_FILES = [
    "wecom_ability_service/domains/user_ops/page_service.py",
    "wecom_ability_service/domains/user_ops/service.py",
    "wecom_ability_service/domains/user_ops/user_ops_deferred_job_service.py",
    "wecom_ability_service/domains/user_ops/hxc_send_config_service.py",
    "wecom_ability_service/http/admin_jobs.py",
    "wecom_ability_service/http/tasks.py",
]

STALE_REGISTRAR_TOKENS = [
    "from .admin_user_ops import",
    "from .admin_user_ops_delivery import",
    "register_admin_user_ops_routes",
    "register_admin_user_ops_delivery_routes",
    '"admin_user_ops": "wecom_ability_service.http.admin_user_ops"',
    '"admin_user_ops_delivery": "wecom_ability_service.http.admin_user_ops_delivery"',
    '("admin_user_ops", register_admin_user_ops_routes)',
    '("admin_user_ops_delivery", register_admin_user_ops_delivery_routes)',
]

RETIRED_LEGACY_ROUTES = [
    "/admin/user-ops/ui",
    "/api/admin/user-ops/overview",
    "/api/admin/user-ops/list",
    "/api/admin/user-ops/send-records",
    "/api/admin/user-ops/send-records/<int:record_id>",
]

WRITE_ROUTES_NOT_LEGACY_REGISTERED = [
    "/api/admin/user-ops/do-not-disturb",
    "/api/admin/user-ops/batch-send/preview",
    "/api/admin/user-ops/batch-send/execute",
    "/api/admin/user-ops/run-deferred-jobs",
    "/api/internal/user-ops/lead-pool/backfill-owner-class-terms",
]

TASK_DISPATCH_FALLBACK_ROUTES = [
    "/api/tasks/private-message",
    "/api/tasks/moment",
    "/api/tasks/group-message",
]

NEXT_USER_OPS_ROUTE_TOKENS = [
    '"/api/admin/user-ops/overview"',
    '"/api/admin/user-ops/list"',
    '"/api/admin/user-ops/send-records"',
    '"/api/admin/user-ops/send-records/{record_id}"',
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
        if lower == ".github/workflows/ci.yml":
            continue
        if lower.startswith(PRODUCTION_CONFIG_PREFIXES):
            return True
        if any(keyword in lower for keyword in PRODUCTION_CONFIG_KEYWORDS):
            if lower.startswith(("docs/", "tests/", "tools/")):
                continue
            return True
    return False


def _legacy_url_map_status() -> dict[str, Any]:
    try:
        from wecom_ability_service import create_app

        app = create_app({"TESTING": True})
        routes = {rule.rule for rule in app.url_map.iter_rules()}
    except Exception:
        return {"import_failed": True}
    status = {route: route in routes for route in RETIRED_LEGACY_ROUTES + WRITE_ROUTES_NOT_LEGACY_REGISTERED}
    status["/api/admin/jobs/deferred-jobs/run"] = "/api/admin/jobs/deferred-jobs/run" in routes
    for route in TASK_DISPATCH_FALLBACK_ROUTES:
        status[route] = route in routes
    return status


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    owner_status = {path: not (REPO_ROOT / path).exists() for path in RETIRED_ROUTE_OWNER_FILES}
    tombstone_files: dict[str, bool] = {}
    if not all(owner_status.values()):
        blockers.append("legacy User Ops readonly route owner file still exists")

    registrar = _read("wecom_ability_service/http/__init__.py")
    stale_imports = [token for token in STALE_REGISTRAR_TOKENS if token in registrar]
    if stale_imports:
        blockers.append("legacy HTTP registrar still references User Ops admin route owner")

    write_fallbacks_preserved = {path: (REPO_ROOT / path).exists() for path in WRITE_FALLBACK_FILES}
    if not all(write_fallbacks_preserved.values()):
        blockers.append("User Ops write/external fallback dependency file was removed")

    legacy_url_map = _legacy_url_map_status()
    if legacy_url_map.get("import_failed"):
        blockers.append("legacy Flask fallback create_app import failed")
    for route in RETIRED_LEGACY_ROUTES:
        if legacy_url_map.get(route):
            blockers.append(f"legacy User Ops readonly route still registered after D4: {route}")
    for route in WRITE_ROUTES_NOT_LEGACY_REGISTERED:
        if legacy_url_map.get(route):
            warnings.append(f"legacy User Ops write route remains HTTP-registered: {route}")
    if legacy_url_map.get("/api/admin/jobs/deferred-jobs/run") is not True:
        blockers.append("admin jobs deferred-job fallback route is missing")
    for route in TASK_DISPATCH_FALLBACK_ROUTES:
        if legacy_url_map.get(route) is not True:
            blockers.append(f"task dispatch fallback route is missing: {route}")

    ops_api = _read("aicrm_next/ops_enrollment/api.py")
    frontend_routes = _read("aicrm_next/frontend_compat/legacy_routes.py")
    repo_source = _read("aicrm_next/ops_enrollment/repo.py")
    next_user_ops_routes = {
        "api": all(token in ops_api for token in NEXT_USER_OPS_ROUTE_TOKENS),
        "admin_pages": '"/admin/user-ops/ui"' in frontend_routes,
        "has_pending_input_card": "激活待录入" in repo_source,
        "routes": [
            "GET /admin/user-ops/ui",
            "GET /api/admin/user-ops/overview",
            "GET /api/admin/user-ops/list",
            "GET /api/admin/user-ops/send-records",
            "GET /api/admin/user-ops/send-records/{record_id}",
        ],
    }
    if not next_user_ops_routes["api"] or not next_user_ops_routes["admin_pages"]:
        blockers.append("AI-CRM Next User Ops readonly routes are incomplete")
    if not next_user_ops_routes["has_pending_input_card"]:
        blockers.append("AI-CRM Next User Ops overview no longer has pending-input card evidence")

    smoke_source = _read("experiments/ai_crm_next/tools/user_ops_readonly_gray_smoke.py")
    smoke_safety_tokens = [
        '"old_write_endpoints_executed": False',
        '"wecom_dispatch_executed": False',
        '"media_upload_executed": False',
        '"deferred_jobs_executed": False',
    ]
    missing_smoke_safety = [token for token in smoke_safety_tokens if token not in smoke_source]
    if missing_smoke_safety:
        blockers.append("User Ops readonly smoke no longer declares write/external safety false")

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
    if "D4: User Ops Old Readonly Routes" not in docs or "Status: retired/tombstoned" not in docs:
        warnings.append("D4 retired/tombstoned status not explicit in docs/legacy_delete_batches.md")
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
        "deleted_files": owner_status,
        "tombstone_files": tombstone_files,
        "stale_imports": stale_imports,
        "write_fallbacks_preserved": write_fallbacks_preserved,
        "legacy_url_map": legacy_url_map,
        "next_user_ops_routes": next_user_ops_routes,
        "legacy_fallback_status": {
            "app_py_default_next": default_next,
            "legacy_flask_app_exists": legacy_fallback_exists,
        },
        "production_config_modified": production_config_modified,
        "changed_files": changed_files,
        "recommendation": "READY_FOR_D4_USER_OPS_RETIREMENT_ACCEPTANCE" if not blockers else "FIX_BLOCKERS",
    }


def _write_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# Legacy D4 User Ops Retirement Check",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- production_config_modified: `{str(report['production_config_modified']).lower()}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Retired Route Owner Files", ""])
    lines.extend([f"- `{path}` absent: `{str(absent).lower()}`" for path, absent in report["deleted_files"].items()])
    lines.extend(["", "## Write Fallbacks Preserved", ""])
    lines.extend([f"- `{path}`: `{str(exists).lower()}`" for path, exists in report["write_fallbacks_preserved"].items()])
    lines.extend(["", "## Stale Imports", ""])
    lines.extend([f"- `{item}`" for item in report["stale_imports"]] or ["- none"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check D4 legacy User Ops readonly route retirement.")
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
