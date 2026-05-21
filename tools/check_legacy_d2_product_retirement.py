from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DELETED_FILES = [
    "wecom_ability_service/http/admin_wechat_pay_products.py",
]

PAYMENT_FILES = [
    "wecom_ability_service/http/wechat_pay.py",
    "wecom_ability_service/http/alipay_pay.py",
    "wecom_ability_service/http/admin_wechat_pay.py",
    "wecom_ability_service/http/admin_alipay_pay.py",
]

PAYMENT_REGISTRAR_KEYS = [
    '"wechat_pay": "wecom_ability_service.http.wechat_pay"',
    '"alipay_pay": "wecom_ability_service.http.alipay_pay"',
    '"admin_wechat_pay": "wecom_ability_service.http.admin_wechat_pay"',
    '"admin_alipay_pay": "wecom_ability_service.http.admin_alipay_pay"',
    '("wechat_pay", register_wechat_pay_routes)',
    '("alipay_pay", register_alipay_pay_routes)',
    '("admin_wechat_pay", register_admin_wechat_pay_routes)',
    '("admin_alipay_pay", register_admin_alipay_pay_routes)',
]

STALE_REGISTRAR_TOKENS = [
    "admin_wechat_pay_products",
    "register_admin_wechat_pay_products_routes",
    '"admin_wechat_pay_products": "wecom_ability_service.http.admin_wechat_pay_products"',
    '("admin_wechat_pay_products", register_admin_wechat_pay_products_routes)',
]

NEXT_PRODUCT_ROUTES = [
    "GET /admin/wechat-pay/products",
    "GET /api/admin/wechat-pay/products",
    "GET /api/admin/wechat-pay/products/{product_id}",
    "GET /p/{page_slug}",
    "GET /api/products/{page_slug}",
]

NEXT_ROUTE_TOKENS = [
    '"/api/admin/wechat-pay/products"',
    '"/api/admin/wechat-pay/products/{product_id}"',
    '"/api/products/{page_slug}"',
    '"/p/{page_slug}"',
    '"/admin/wechat-pay/products"',
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


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    deleted_status = {path: not (REPO_ROOT / path).exists() for path in DELETED_FILES}
    tombstone_files: dict[str, bool] = {}
    if not all(deleted_status.values()):
        blockers.append("legacy product management route file still exists")

    registrar = _read("wecom_ability_service/http/__init__.py")
    stale_imports = [token for token in STALE_REGISTRAR_TOKENS if token in registrar]
    if stale_imports:
        blockers.append("legacy HTTP registrar still references D2 product management route module")

    payment_files_preserved = {path: (REPO_ROOT / path).exists() for path in PAYMENT_FILES}
    missing_payment_files = [path for path, exists in payment_files_preserved.items() if not exists]
    if missing_payment_files:
        blockers.append("payment/checkout fallback files were removed")

    payment_registrar_missing = [token for token in PAYMENT_REGISTRAR_KEYS if token not in registrar]
    if payment_registrar_missing:
        blockers.append("payment/checkout registrar entries are missing")

    commerce_api = _read("aicrm_next/commerce/api.py")
    frontend_routes = _read("aicrm_next/frontend_compat/legacy_routes.py")
    next_product_routes = {
        "api": all(token in commerce_api for token in NEXT_ROUTE_TOKENS[:4]),
        "admin_pages": NEXT_ROUTE_TOKENS[4] in frontend_routes,
        "routes": NEXT_PRODUCT_ROUTES,
    }
    if not next_product_routes["api"] or not next_product_routes["admin_pages"]:
        blockers.append("AI-CRM Next product readonly routes are incomplete")

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
    if "D2: Product Old Readonly Routes" not in docs or "Status: retired/deleted" not in docs:
        warnings.append("D2 retired/deleted status not explicit in docs/legacy_delete_batches.md")
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
        "deleted_files": deleted_status,
        "tombstone_files": tombstone_files,
        "stale_imports": stale_imports,
        "payment_files_preserved": payment_files_preserved,
        "payment_registrar_missing": payment_registrar_missing,
        "next_product_routes": next_product_routes,
        "legacy_fallback_status": {
            "app_py_default_next": default_next,
            "legacy_flask_app_exists": legacy_fallback_exists,
        },
        "production_config_modified": production_config_modified,
        "changed_files": changed_files,
        "recommendation": "READY_FOR_D2_PRODUCT_RETIREMENT_ACCEPTANCE" if not blockers else "FIX_BLOCKERS",
    }


def _write_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# Legacy D2 Product Retirement Check",
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
    lines.extend(["", "## Payment Files Preserved", ""])
    lines.extend([f"- `{path}`: `{str(exists).lower()}`" for path, exists in report["payment_files_preserved"].items()])
    lines.extend(["", "## Stale Imports", ""])
    lines.extend([f"- `{item}`" for item in report["stale_imports"]] or ["- none"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check D2 legacy Product Management route retirement.")
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
