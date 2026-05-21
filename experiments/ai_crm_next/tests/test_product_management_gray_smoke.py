from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from tools import product_management_gray_smoke as gray_smoke

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _args(*, include_fake_writes: bool = False, next_testclient: bool = True, next_base_url: str = "") -> Namespace:
    return Namespace(
        next_testclient=next_testclient,
        next_base_url=next_base_url,
        include_fake_writes=include_fake_writes,
        output_md="/tmp/unused.md",
        output_json="/tmp/unused.json",
    )


def test_default_smoke_endpoints_are_get_only() -> None:
    report = gray_smoke.run_smoke(_args())
    assert report["ok"] is True
    assert all(item["method"] == "GET" for item in report["route_results"])
    assert report["side_effect_safety"]["default_endpoints_get_only"] is True


def test_checkout_endpoints_are_not_in_default_smoke() -> None:
    report = gray_smoke.run_smoke(_args())
    paths = {item["path"] for item in report["route_results"]}
    assert not paths.intersection(gray_smoke.CHECKOUT_ENDPOINTS)
    assert report["side_effect_safety"]["checkout_executed"] is False
    assert report["side_effect_safety"]["payment_provider_called"] is False
    assert any(item["reason"] == "checkout_not_in_scope" for item in report["skipped"])


def test_old_write_endpoints_are_never_executed() -> None:
    report = gray_smoke.run_smoke(_args())
    assert report["side_effect_safety"]["old_write_endpoints_executed"] is False
    assert report["side_effect_safety"]["external_payment_executed"] is False


def test_default_smoke_covers_product_read_routes() -> None:
    report = gray_smoke.run_smoke(_args())
    names = {item["name"] for item in report["route_results"]}
    assert "admin_products_page" in names
    assert "admin_products_list" in names
    assert "admin_product_detail" in names
    assert "public_product_page" in names
    assert "public_product_api" in names


def test_fake_writes_require_explicit_include_fake_writes() -> None:
    default_report = gray_smoke.run_smoke(_args())
    assert not any(item["method"] in {"POST", "PUT", "DELETE"} for item in default_report["route_results"])

    write_report = gray_smoke.run_smoke(_args(include_fake_writes=True))
    assert write_report["ok"] is True
    assert {"POST", "PUT", "DELETE"} <= {item["method"] for item in write_report["route_results"]}
    assert all(item["path"] not in gray_smoke.CHECKOUT_ENDPOINTS for item in write_report["route_results"])


def test_fake_write_mode_only_targets_next_testclient() -> None:
    report = gray_smoke.run_smoke(_args(include_fake_writes=True, next_testclient=False, next_base_url="http://127.0.0.1:8000"))
    assert report["ok"] is False
    assert any(item["reason"] == "fake_writes_require_next_testclient" for item in report["blockers"])


def test_fake_write_mode_does_not_execute_checkout() -> None:
    report = gray_smoke.run_smoke(_args(include_fake_writes=True))
    assert report["ok"] is True
    assert report["side_effect_safety"]["checkout_executed"] is False
    assert report["side_effect_safety"]["payment_provider_called"] is False
    assert not {item["path"] for item in report["route_results"]}.intersection(gray_smoke.CHECKOUT_ENDPOINTS)


def test_report_includes_side_effect_safety(tmp_path: Path) -> None:
    report = gray_smoke.run_smoke(_args())
    output_md = tmp_path / "product_gray.md"
    output_json = tmp_path / "product_gray.json"
    gray_smoke.write_markdown_report(report, output_md)
    gray_smoke.write_json_report(report, output_json)
    assert "old_write_endpoints_executed" in output_md.read_text(encoding="utf-8")
    assert "checkout_executed" in output_md.read_text(encoding="utf-8")
    assert "side_effect_safety" in output_json.read_text(encoding="utf-8")


def test_report_fails_if_route_returns_500(monkeypatch) -> None:
    def fake_request(_client, method: str, path: str, payload=None):
        if path == "/api/admin/wechat-pay/products":
            return 500, {"ok": False}
        return 200, {"ok": True, "product": {"id": "prod_fake"}, "items": [], "total": 0, "limit": 50, "offset": 0}

    monkeypatch.setattr(gray_smoke, "_request_testclient", fake_request)
    report = gray_smoke.run_smoke(_args())
    assert report["ok"] is False
    assert any(item["reason"] == "route_returned_5xx" for item in report["blockers"])


def test_route_cutover_manifest_includes_all_product_routes() -> None:
    text = (PROJECT_ROOT / "docs" / "product_management_route_cutover_manifest.md").read_text(encoding="utf-8")
    required_routes = [
        "/admin/wechat-pay/products",
        "/api/admin/wechat-pay/products",
        "/api/admin/wechat-pay/products/{product_id}",
        "/api/admin/wechat-pay/products/{product_id}/enable",
        "/api/admin/wechat-pay/products/{product_id}/disable",
        "/p/{page_slug}",
        "/api/products/{page_slug}",
        "/api/checkout/wechat",
        "/api/checkout/alipay",
    ]
    for route in required_routes:
        assert route in text
    for method in ["GET", "POST", "PUT", "DELETE"]:
        assert f"| {method} |" in text
    assert "no_production" in text
    assert "payment_external" in text


def test_gray_release_plan_does_not_mark_production_ready() -> None:
    text = (PROJECT_ROOT / "docs" / "product_management_gray_release_plan.md").read_text(encoding="utf-8")
    assert "production_ready |" not in text
    assert "status: production_ready" not in text
    assert "production replacement: not ready" in text
    assert "真实支付 checkout" in text


def test_product_gray_smoke_tool_does_not_import_old_backend() -> None:
    assert Path(gray_smoke.__file__).resolve().relative_to(PROJECT_ROOT.parents[1]) == Path("tools/product_management_gray_smoke.py")
    report = gray_smoke.run_smoke(_args())
    safety = report["side_effect_safety"]
    assert safety["old_write_endpoints_executed"] is False
    assert safety["payment_provider_called"] is False
    assert safety["checkout_executed"] is False
    assert safety["external_payment_executed"] is False
