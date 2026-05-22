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
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/image-library") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/image-library") == "aicrm_next.media_library.api"


def test_high_risk_legacy_facade_routes_remain_production_compat_owned():
    result = checker.run_check()
    samples = result["resolution_samples"]

    assert _owner_for(samples, "POST", "/wecom/external-contact/callback") == "production_compat"
    assert _endpoint_for(samples, "POST", "/wecom/external-contact/callback") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due") == "production_compat"
    assert _endpoint_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/api/h5/wechat-pay/legacy-probe") == "production_compat"
    assert _endpoint_for(samples, "GET", "/api/h5/wechat-pay/legacy-probe") == "aicrm_next.production_compat.api"


def test_checker_reports_no_shadowed_exact_routes_or_blockers():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["shadowed_exact_routes"] == []
