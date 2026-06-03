from __future__ import annotations

import inspect
from pathlib import Path

from aicrm_next.customer_read_model import api as customer_api


ROOT = Path(__file__).resolve().parents[1]


TARGET_FUNCTIONS = [
    customer_api.get_sidebar_customer_context,
    customer_api.get_sidebar_profile,
    customer_api.get_sidebar_tags,
    customer_api.get_sidebar_lead_pool_status,
    customer_api.get_sidebar_signup_tag_status,
    customer_api.get_sidebar_marketing_status,
]


def test_sidebar_readonly_target_routes_do_not_call_legacy_sidebar_facade() -> None:
    combined = "\n".join(inspect.getsource(func) for func in TARGET_FUNCTIONS)

    assert "legacy_sidebar_read_facade" not in combined
    assert "forward_to_legacy_flask" not in combined
    assert "wecom_ability_service" not in combined


def test_sidebar_readonly_routes_are_not_production_compat_forwards() -> None:
    source = (ROOT / "aicrm_next/production_compat/api.py").read_text(encoding="utf-8")

    for route in [
        "/api/sidebar/customer-context",
        "/api/sidebar/profile",
        "/api/sidebar/tags",
        "/api/sidebar/binding-status",
        "/api/sidebar/contact-binding-status",
        "/api/sidebar/lead-pool/status",
        "/api/sidebar/signup-tags/status",
        "/api/sidebar/marketing-status\", methods=[\"GET",
    ]:
        assert route not in source

    assert "/api/sidebar/jssdk-config" not in source

    for write_route in [
        "/api/sidebar/bind-mobile",
        "/api/sidebar/lead-pool/upsert-class-term",
        "/api/sidebar/signup-tags/mark",
        "/api/sidebar/marketing-status/mark-enrolled",
        "/api/sidebar/v2/materials/send",
    ]:
        assert write_route not in source
