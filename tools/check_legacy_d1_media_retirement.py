from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DELETED_FILES = [
    "wecom_ability_service/http/image_library_endpoint.py",
    "wecom_ability_service/http/image_library_create.py",
    "wecom_ability_service/http/attachment_library_endpoint.py",
    "wecom_ability_service/http/miniprogram_library_endpoint.py",
]

STALE_REGISTRAR_TOKENS = [
    "image_library_endpoint",
    "image_library_create",
    "attachment_library_endpoint",
    "miniprogram_library_endpoint",
    "register_image_library_routes",
    "register_attachment_library_routes",
    "register_miniprogram_library_routes",
    '"image_library": "wecom_ability_service.http.image_library_endpoint"',
    '"attachment_library": "wecom_ability_service.http.attachment_library_endpoint"',
    '"miniprogram_library": "wecom_ability_service.http.miniprogram_library_endpoint"',
]

NEXT_MEDIA_ROUTES = [
    "GET /admin/image-library",
    "GET /api/admin/image-library",
    "GET /admin/attachment-library",
    "GET /api/admin/attachment-library",
    "GET /admin/miniprogram-library",
    "GET /api/admin/miniprogram-library",
]

NEXT_ROUTE_TOKENS = [
    '"/api/admin/image-library"',
    '"/api/admin/attachment-library"',
    '"/api/admin/miniprogram-library"',
    '"/admin/image-library"',
    '"/admin/attachment-library"',
    '"/admin/miniprogram-library"',
]

PRODUCTION_CONFIG_PREFIXES = ("deploy/", ".github/")
PRODUCTION_CONFIG_KEYWORDS = ("nginx", "production", "systemd", "supervisor", "docker-compose")


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _git_changed_files() -> list[str]:
    changed: set[str] = set()
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        result = None
    if result is not None:
        changed.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    try:
        worktree = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        changed.update(line.strip() for line in worktree.stdout.splitlines() if line.strip())
        changed.update(line.strip() for line in staged.stdout.splitlines() if line.strip())
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        changed.update(line.strip() for line in untracked.stdout.splitlines() if line.strip())
    except Exception:
        pass
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


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    deleted_status = {path: not (REPO_ROOT / path).exists() for path in DELETED_FILES}
    missing_deletions = [path for path, is_deleted in deleted_status.items() if not is_deleted]
    if missing_deletions:
        blockers.append("legacy media route files still exist")

    registrar_path = "wecom_ability_service/http/__init__.py"
    registrar = _read(registrar_path)
    stale_imports = [token for token in STALE_REGISTRAR_TOKENS if token in registrar]
    if stale_imports:
        blockers.append("legacy HTTP registrar still references D1 media route modules")

    media_api = _read("aicrm_next/media_library/api.py")
    frontend_routes = _read("aicrm_next/frontend_compat/legacy_routes.py")
    next_media_routes = {
        "api": all(token in media_api for token in NEXT_ROUTE_TOKENS[:3]),
        "admin_pages": all(token in frontend_routes for token in NEXT_ROUTE_TOKENS[3:]),
        "routes": NEXT_MEDIA_ROUTES,
    }
    if not next_media_routes["api"] or not next_media_routes["admin_pages"]:
        blockers.append("AI-CRM Next media routes are incomplete")

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
    if "D1: Media Old Readonly Routes" not in docs or "Status: retired/deleted" not in docs:
        warnings.append("D1 retired/deleted status not explicit in docs/legacy_delete_batches.md")
    for batch in ["D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"]:
        section_marker = f"## {batch}:"
        after = docs.split(section_marker, 1)[1] if section_marker in docs else ""
        status_line = next((line.strip().lower() for line in after.splitlines() if line.strip().lower().startswith("status:")), "")
        if status_line.startswith("status: retired") or status_line.startswith("status: deleted"):
            blockers.append(f"{batch} is incorrectly marked retired/deleted")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "deleted_files": deleted_status,
        "stale_imports": stale_imports,
        "next_media_routes": next_media_routes,
        "legacy_fallback_status": {
            "app_py_default_next": default_next,
            "legacy_flask_app_exists": legacy_fallback_exists,
        },
        "production_config_modified": production_config_modified,
        "changed_files": changed_files,
        "recommendation": "READY_FOR_D1_MEDIA_RETIREMENT_ACCEPTANCE" if not blockers else "FIX_BLOCKERS",
    }


def _write_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# Legacy D1 Media Retirement Check",
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
    lines.extend(["", "## Stale Imports", ""])
    lines.extend([f"- `{item}`" for item in report["stale_imports"]] or ["- none"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check D1 legacy Media Library route retirement.")
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
