from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_ROUTE_FILE = "wecom_ability_service/http/admin_wechat_pay_products.py"
PAYMENT_ROUTE_FILES = [
    "wecom_ability_service/http/wechat_pay.py",
    "wecom_ability_service/http/alipay_pay.py",
    "wecom_ability_service/http/admin_wechat_pay.py",
    "wecom_ability_service/http/admin_alipay_pay.py",
]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_old_admin_wechat_pay_products_file_is_absent_or_tombstone() -> None:
    path = REPO_ROOT / PRODUCT_ROUTE_FILE
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8").lower()
    assert "tombstone" in content
    assert "def register_routes" not in content


def test_old_http_registrar_has_no_admin_wechat_pay_products_import_or_register_entry() -> None:
    content = _read("wecom_ability_service/http/__init__.py")
    forbidden_tokens = [
        "from .admin_wechat_pay_products",
        "register_admin_wechat_pay_products_routes",
        '"admin_wechat_pay_products": "wecom_ability_service.http.admin_wechat_pay_products"',
        '("admin_wechat_pay_products", register_admin_wechat_pay_products_routes)',
    ]
    assert [token for token in forbidden_tokens if token in content] == []


def test_old_payment_route_modules_and_registrars_still_exist() -> None:
    content = _read("wecom_ability_service/http/__init__.py")
    for path in PAYMENT_ROUTE_FILES:
        assert (REPO_ROOT / path).exists(), path
    for token in [
        '"wechat_pay": "wecom_ability_service.http.wechat_pay"',
        '"alipay_pay": "wecom_ability_service.http.alipay_pay"',
        '"admin_wechat_pay": "wecom_ability_service.http.admin_wechat_pay"',
        '"admin_alipay_pay": "wecom_ability_service.http.admin_alipay_pay"',
        '("wechat_pay", register_wechat_pay_routes)',
        '("alipay_pay", register_alipay_pay_routes)',
        '("admin_wechat_pay", register_admin_wechat_pay_routes)',
        '("admin_alipay_pay", register_admin_alipay_pay_routes)',
    ]:
        assert token in content


def test_aicrm_next_commerce_package_exists() -> None:
    assert (REPO_ROOT / "aicrm_next" / "commerce" / "api.py").exists()
    assert (REPO_ROOT / "aicrm_next" / "commerce" / "repo.py").exists()


def test_product_admin_routes_are_forwarded_to_legacy_admin_runtime() -> None:
    from tools import check_production_route_resolution as checker

    result = checker.run_check()
    samples = result["resolution_samples"]
    product_paths = {
        "/admin/wechat-pay/products",
        "/admin/wechat-pay/products/new",
        "/api/admin/wechat-pay/products",
        "/api/admin/wechat-pay/products/1",
        "/api/admin/wechat-pay/products/1/share",
    }
    matched = {item["path"]: item for item in samples if item["path"] in product_paths}

    assert set(matched) == product_paths
    for item in matched.values():
        assert item["route_owner"] == "production_compat"
        assert item["endpoint_module"] == "aicrm_next.production_compat.api"


def test_public_product_routes_are_forwarded_to_legacy_in_production() -> None:
    from tools import check_production_route_resolution as checker

    result = checker.run_check()
    samples = result["resolution_samples"]
    public_paths = {
        "/p/prd_20260518095708_9f77db",
        "/api/products/prd_20260518095708_9f77db",
    }
    matched = {item["path"]: item for item in samples if item["path"] in public_paths}

    assert set(matched) == public_paths
    for item in matched.values():
        assert item["route_owner"] == "production_compat"
        assert item["endpoint_module"] == "aicrm_next.production_compat.api"


def test_next_checkout_is_not_executed_by_product_readonly_scope() -> None:
    from tools import product_management_gray_smoke as gray_smoke

    args = gray_smoke.build_parser().parse_args(["--next-testclient", "--output-md", "/tmp/product.md", "--output-json", "/tmp/product.json"])
    report = gray_smoke.run_smoke(args)
    safety = report["side_effect_safety"]
    assert safety["checkout_executed"] is False
    assert safety["payment_provider_called"] is False
    assert safety["external_payment_executed"] is False
    assert safety["checkout_endpoints_in_default_smoke"] is False
    assert any(item["reason"] == "checkout_not_in_scope" for item in report["skipped"])


def test_app_py_default_is_still_next() -> None:
    content = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in content
    assert "uvicorn.run(NEXT_APP_IMPORT" in content
    assert "command = args.command or \"run\"" in content


def test_legacy_fallback_still_exists() -> None:
    assert (REPO_ROOT / "legacy_flask_app.py").exists()
    help_result = subprocess.run(
        ["python3", "legacy_flask_app.py", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "legacy Flask fallback" in help_result.stdout or "legacy Flask fallback" in help_result.stderr


def test_deploy_and_production_config_not_modified_by_d2() -> None:
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    forbidden = [
        path
        for path in changed
        if path.startswith("deploy/")
        or (path.startswith(".github/") and path != ".github/workflows/ci.yml")
        or any(keyword in path.lower() for keyword in ["nginx", "systemd", "supervisor", "docker-compose", "production"])
        and not path.startswith(("aicrm_next/production_compat/", "docs/", "tests/", "tools/"))
    ]
    assert forbidden == []


def test_d7_to_d9_docs_are_not_marked_retired_or_deleted() -> None:
    content = _read("docs/legacy_delete_batches.md")
    for batch in ["D7", "D8", "D9"]:
        section = content.split(f"## {batch}:", 1)[1].split("## ", 1)[0]
        status_line = next((line.strip().lower() for line in section.splitlines() if line.strip().lower().startswith("status:")), "")
        assert not status_line.startswith("status: retired")
        assert not status_line.startswith("status: deleted")


def test_d2_retirement_checker_returns_ok(tmp_path: Path) -> None:
    output_md = tmp_path / "d2.md"
    output_json = tmp_path / "d2.json"
    subprocess.run(
        [
            "python3",
            "tools/check_legacy_d2_product_retirement.py",
            "--output-md",
            str(output_md),
            "--output-json",
            str(output_json),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["production_config_modified"] is False
    assert payload["payment_files_preserved"]["wecom_ability_service/http/wechat_pay.py"] is True
