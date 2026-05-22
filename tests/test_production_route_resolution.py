from __future__ import annotations

from tools import check_production_route_resolution as checker


def _owner_for(samples: list[dict], method: str, path: str) -> str:
    for item in samples:
        if item["method"] == method and item["path"] == path:
            return str(item["route_owner"])
    raise AssertionError(f"missing sample {method} {path}")


def _endpoint_for(samples: list[dict], method: str, path: str) -> str:
    for item in samples:
        if item["method"] == method and item["path"] == path:
            return str(item["endpoint_module"])
    raise AssertionError(f"missing sample {method} {path}")


def test_next_exact_routes_are_not_caught_by_production_compat_wildcards():
    result = checker.run_check()
    samples = result["resolution_samples"]

    assert _owner_for(samples, "GET", "/api/customers") == "next"
    assert _endpoint_for(samples, "GET", "/api/customers") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/messages/wx_ext_001/recent") == "next"
    assert _endpoint_for(samples, "GET", "/api/messages/wx_ext_001/recent") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/admin/image-library") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/image-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/sidebar/bind-mobile") == "next"
    assert _endpoint_for(samples, "GET", "/sidebar/bind-mobile") == "aicrm_next.frontend_compat.legacy_routes"
    assert _owner_for(samples, "GET", "/api/sidebar/contact-binding-status") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/contact-binding-status") == "aicrm_next.identity_contact.api"
    assert _owner_for(samples, "GET", "/api/sidebar/customer-context") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/customer-context") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/admin/customers/profile") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/customers/profile") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/admin/customers/profile/tags") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/customers/profile/tags") == "aicrm_next.customer_read_model.api"


def test_high_risk_legacy_facade_routes_remain_production_compat_owned():
    result = checker.run_check()
    samples = result["resolution_samples"]

    assert _owner_for(samples, "POST", "/wecom/external-contact/callback") == "production_compat"
    assert _endpoint_for(samples, "POST", "/wecom/external-contact/callback") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due") == "production_compat"
    assert _endpoint_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/admin/wechat-pay/products") == "production_compat"
    assert _endpoint_for(samples, "GET", "/admin/wechat-pay/products") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/admin/wechat-pay/products/new") == "production_compat"
    assert _endpoint_for(samples, "GET", "/admin/wechat-pay/products/new") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products") == "production_compat"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products/1") == "production_compat"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products/1") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products/1/share") == "production_compat"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products/1/share") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/p/prd_20260518095708_9f77db") == "production_compat"
    assert _endpoint_for(samples, "GET", "/p/prd_20260518095708_9f77db") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/api/products/prd_20260518095708_9f77db") == "production_compat"
    assert _endpoint_for(samples, "GET", "/api/products/prd_20260518095708_9f77db") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/programs/3/setup/basic") == "production_compat"
    assert (
        _endpoint_for(samples, "POST", "/api/admin/automation-conversion/programs/3/setup/basic")
        == "aicrm_next.production_compat.api"
    )
    assert (
        _owner_for(samples, "POST", "/api/admin/automation-conversion/settings/default-channel/generate")
        == "production_compat"
    )
    assert (
        _endpoint_for(samples, "POST", "/api/admin/automation-conversion/settings/default-channel/generate")
        == "aicrm_next.production_compat.api"
    )
    assert (
        _owner_for(samples, "GET", "/api/admin/automation-conversion/default-channel-settings")
        == "production_compat"
    )
    assert (
        _endpoint_for(samples, "GET", "/api/admin/automation-conversion/default-channel-settings")
        == "aicrm_next.production_compat.api"
    )
    assert (
        _owner_for(samples, "POST", "/api/admin/automation-conversion/default-channel-settings/generate-qr")
        == "production_compat"
    )
    assert (
        _endpoint_for(samples, "POST", "/api/admin/automation-conversion/default-channel-settings/generate-qr")
        == "aicrm_next.production_compat.api"
    )
    assert (
        _owner_for(samples, "GET", "/api/admin/automation-conversion/profile-segment-templates/options")
        == "production_compat"
    )
    assert (
        _endpoint_for(samples, "GET", "/api/admin/automation-conversion/profile-segment-templates/options")
        == "aicrm_next.production_compat.api"
    )
    assert _owner_for(samples, "GET", "/api/admin/automation-conversion/agents/options") == "production_compat"
    assert (
        _endpoint_for(samples, "GET", "/api/admin/automation-conversion/agents/options")
        == "aicrm_next.production_compat.api"
    )
    assert _owner_for(samples, "GET", "/api/h5/wechat-pay/legacy-probe") == "production_compat"
    assert _endpoint_for(samples, "GET", "/api/h5/wechat-pay/legacy-probe") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "POST", "/api/sidebar/bind-mobile") == "production_compat"
    assert _endpoint_for(samples, "POST", "/api/sidebar/bind-mobile") == "aicrm_next.production_compat.api"


def test_checker_reports_no_unexpected_shadowed_exact_routes_or_blockers():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["blockers"] == []
    unexpected_shadowed = [
        item
        for item in result["shadowed_exact_routes"]
        if item["manifest_route_pattern"]
        not in {
            "/admin/wechat-pay/products*",
            "/api/admin/wechat-pay/products*",
            "/p/{page_slug}",
            "/api/products*",
        }
    ]
    assert unexpected_shadowed == []
