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

DELETED_FILES = [
    "wecom_ability_service/http/customer_center.py",
    "wecom_ability_service/http/customer_timeline.py",
]

PRESERVED_FALLBACK_FILES = [
    "wecom_ability_service/http/archive.py",
    "wecom_ability_service/http/contacts.py",
    "wecom_ability_service/http/identity.py",
]

PRESERVED_DEPENDENCY_MARKERS = [
    "wecom_ability_service/customer_center/LEGACY_DEPENDENCY_FALLBACK.md",
    "wecom_ability_service/customer_timeline/LEGACY_DEPENDENCY_FALLBACK.md",
]

STALE_REGISTRAR_TOKENS = [
    "from .customer_center import",
    "from .customer_timeline import",
    "register_customer_center_routes",
    "register_customer_timeline_routes",
    '"customer_center": "wecom_ability_service.http.customer_center"',
    '"customer_timeline": "wecom_ability_service.http.customer_timeline"',
    '("customer_center", register_customer_center_routes)',
    '("customer_timeline", register_customer_timeline_routes)',
]

NEXT_CUSTOMER_ROUTE_TOKENS = [
    '"/api/customers"',
    '"/api/customers/{external_userid}"',
    '"/api/customers/{external_userid}/timeline"',
    '"/api/messages/{external_userid}/recent"',
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


def _legacy_url_map_status() -> dict[str, bool]:
    try:
        from wecom_ability_service import create_app

        app = create_app({"TESTING": True})
        routes = {rule.rule for rule in app.url_map.iter_rules()}
    except Exception:
        return {"import_failed": True}
    return {
        "/admin/customers": "/admin/customers" in routes,
        "/api/customers": "/api/customers" in routes,
        "/api/customers/<external_userid>": "/api/customers/<external_userid>" in routes,
        "/api/customers/<external_userid>/timeline": "/api/customers/<external_userid>/timeline" in routes,
        "/api/messages/<external_userid>/recent": "/api/messages/<external_userid>/recent" in routes,
    }


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    deleted_status = {path: not (REPO_ROOT / path).exists() for path in DELETED_FILES}
    if not all(deleted_status.values()):
        blockers.append("legacy customer read-model HTTP route files still exist")

    dependency_markers = {path: (REPO_ROOT / path).exists() for path in PRESERVED_DEPENDENCY_MARKERS}
    if not all(dependency_markers.values()):
        blockers.append("mixed customer dependency fallback markers are missing")

    registrar = _read("wecom_ability_service/http/__init__.py")
    stale_imports = [token for token in STALE_REGISTRAR_TOKENS if token in registrar]
    if stale_imports:
        blockers.append("legacy HTTP registrar still references D3 customer route modules")

    preserved_fallback_files = {path: (REPO_ROOT / path).exists() for path in PRESERVED_FALLBACK_FILES}
    if not all(preserved_fallback_files.values()):
        blockers.append("archive/contacts/identity fallback file was removed")

    legacy_url_map = _legacy_url_map_status()
    if legacy_url_map.get("import_failed"):
        blockers.append("legacy Flask fallback create_app import failed")
    for retired_route in (
        "/admin/customers",
        "/api/customers",
        "/api/customers/<external_userid>",
        "/api/customers/<external_userid>/timeline",
    ):
        if legacy_url_map.get(retired_route):
            blockers.append(f"legacy route still registered after D3: {retired_route}")
    if legacy_url_map.get("/api/messages/<external_userid>/recent") is not True:
        blockers.append("legacy archive recent messages fallback route is missing")

    customer_api = _read("aicrm_next/customer_read_model/api.py")
    frontend_routes = _read("aicrm_next/frontend_compat/legacy_routes.py")
    next_customer_routes = {
        "api": all(token in customer_api for token in NEXT_CUSTOMER_ROUTE_TOKENS),
        "admin_pages": '"/admin/customers"' in frontend_routes,
        "routes": [
            "GET /admin/customers",
            "GET /api/customers",
            "GET /api/customers/{external_userid}",
            "GET /api/customers/{external_userid}/timeline",
            "GET /api/messages/{external_userid}/recent",
        ],
    }
    if not next_customer_routes["api"] or not next_customer_routes["admin_pages"]:
        blockers.append("AI-CRM Next customer readonly routes are incomplete")

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
    if "D3: Customer Old Readonly Routes" not in docs or "Status: retired/deleted" not in docs:
        warnings.append("D3 retired/deleted status not explicit in docs/legacy_delete_batches.md")
    if "`wecom_ability_service/http/archive.py`" not in docs:
        warnings.append("D3 docs do not explicitly record archive.py preservation")
    for batch in ["D4", "D5", "D6", "D7", "D8", "D9"]:
        marker = f"## {batch}:"
        section = docs.split(marker, 1)[1] if marker in docs else ""
        status_line = next((line.strip().lower() for line in section.splitlines() if line.strip().lower().startswith("status:")), "")
        if status_line.startswith("status: retired") or status_line.startswith("status: deleted"):
            blockers.append(f"{batch} is incorrectly marked retired/deleted")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "deleted_files": deleted_status,
        "tombstone_files": {},
        "dependency_fallback_markers": dependency_markers,
        "stale_imports": stale_imports,
        "archive_contacts_identity_preserved": preserved_fallback_files,
        "legacy_url_map": legacy_url_map,
        "next_customer_routes": next_customer_routes,
        "legacy_fallback_status": {
            "app_py_default_next": default_next,
            "legacy_flask_app_exists": legacy_fallback_exists,
        },
        "production_config_modified": production_config_modified,
        "changed_files": changed_files,
        "recommendation": "READY_FOR_D3_CUSTOMER_RETIREMENT_ACCEPTANCE" if not blockers else "FIX_BLOCKERS",
    }


def _write_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# Legacy D3 Customer Retirement Check",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- recommendation: `{report['recommendation']}`",
        f"- production_config_modified: `{str(report['production_config_modified']).lower()}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- none"])
    lines.extend(["", "## Deleted Files", ""])
    lines.extend([f"- `{path}`: `{str(is_deleted).lower()}`" for path, is_deleted in report["deleted_files"].items()])
    lines.extend(["", "## Preserved Fallback Files", ""])
    lines.extend(
        f"- `{path}`: `{str(exists).lower()}`"
        for path, exists in report["archive_contacts_identity_preserved"].items()
    )
    lines.extend(["", "## Stale Imports", ""])
    lines.extend([f"- `{item}`" for item in report["stale_imports"]] or ["- none"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check D3 legacy Customer Read Model route retirement.")
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
