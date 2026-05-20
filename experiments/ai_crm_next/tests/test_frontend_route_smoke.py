from __future__ import annotations

from conftest import make_client
from tools.capture_frontend_screenshots import FORBIDDEN_PLACEHOLDER_TEXT, FRONTEND_ROUTES


def test_frontend_route_manifest_covers_required_routes() -> None:
    routes = {spec.route for spec in FRONTEND_ROUTES}
    assert "/admin" in routes
    assert "/admin/customers" in routes
    assert "/admin/user-ops/ui" in routes
    assert "/admin/questionnaires" in routes
    assert "/admin/questionnaires/ui" in routes
    assert "/admin/automation-conversion" in routes
    assert "/admin/wechat-pay/products" in routes
    assert "/admin/wechat-pay/transactions" in routes
    assert "/admin/alipay/transactions" in routes
    assert "/admin/image-library" in routes
    assert "/admin/attachment-library" in routes
    assert "/admin/miniprogram-library" in routes
    assert "/s/hxc-activation-v1" in routes
    assert "/p/course-masked-001" in routes


def test_frontend_routes_smoke_against_legacy_adapter() -> None:
    client = make_client()
    for spec in FRONTEND_ROUTES:
        response = client.get(spec.route)
        assert response.status_code == spec.expected_status, spec.route
        html = response.text
        for token in spec.must_contain_text:
            assert token in html, f"{spec.route} missing {token}"
        for forbidden in FORBIDDEN_PLACEHOLDER_TEXT:
            assert forbidden not in html, f"{spec.route} contains forbidden placeholder {forbidden}"


def test_frontend_routes_are_get_only_for_smoke_manifest() -> None:
    assert all(spec.route.startswith(("/admin", "/s/", "/p/")) for spec in FRONTEND_ROUTES)
