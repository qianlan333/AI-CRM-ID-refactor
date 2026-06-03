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
    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/media/upload") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/cloud-orchestrator/media/upload") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/admin/cloud-orchestrator/campaigns") == "next"
    assert _endpoint_for(samples, "GET", "/admin/cloud-orchestrator/campaigns") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/members") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/members") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/api/admin/image-library") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/image-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/image-library") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/image-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/image-library/from-url") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/image-library/from-url") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/image-library/from-base64") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/image-library/from-base64") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/image-library/upload") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/image-library/upload") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/image-library/image_masked_001") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/image-library/image_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "PUT", "/api/admin/image-library/image_masked_001") == "next"
    assert _endpoint_for(samples, "PUT", "/api/admin/image-library/image_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "DELETE", "/api/admin/image-library/image_masked_001") == "next"
    assert _endpoint_for(samples, "DELETE", "/api/admin/image-library/image_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/image-library/image_masked_001/thumbnail") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/image-library/image_masked_001/thumbnail") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/image-library/image_masked_001/variants/thumb_160") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/image-library/image_masked_001/variants/thumb_160") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/attachment-library") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/attachment-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/attachment-library") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/attachment-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/attachment-library/upload") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/attachment-library/upload") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/attachment-library/attachment_masked_001") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/attachment-library/attachment_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "PUT", "/api/admin/attachment-library/attachment_masked_001") == "next"
    assert _endpoint_for(samples, "PUT", "/api/admin/attachment-library/attachment_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "DELETE", "/api/admin/attachment-library/attachment_masked_001") == "next"
    assert _endpoint_for(samples, "DELETE", "/api/admin/attachment-library/attachment_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/miniprogram-library") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/miniprogram-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/miniprogram-library") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/miniprogram-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/miniprogram-library/miniprogram_masked_001") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/miniprogram-library/miniprogram_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "PUT", "/api/admin/miniprogram-library/miniprogram_masked_001") == "next"
    assert _endpoint_for(samples, "PUT", "/api/admin/miniprogram-library/miniprogram_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "DELETE", "/api/admin/miniprogram-library/miniprogram_masked_001") == "next"
    assert _endpoint_for(samples, "DELETE", "/api/admin/miniprogram-library/miniprogram_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/admin/image-library") == "next"
    assert _endpoint_for(samples, "GET", "/admin/image-library") == "aicrm_next.frontend_compat.legacy_routes"
    assert _owner_for(samples, "GET", "/admin/attachment-library") == "next"
    assert _endpoint_for(samples, "GET", "/admin/attachment-library") == "aicrm_next.frontend_compat.legacy_routes"
    assert _owner_for(samples, "GET", "/admin/miniprogram-library") == "next"
    assert _endpoint_for(samples, "GET", "/admin/miniprogram-library") == "aicrm_next.frontend_compat.legacy_routes"
    assert _owner_for(samples, "GET", "/admin/questionnaires") == "next"
    assert _endpoint_for(samples, "GET", "/admin/questionnaires") == "aicrm_next.frontend_compat.legacy_routes"
    assert _owner_for(samples, "GET", "/admin/questionnaires/new") == "next"
    assert _endpoint_for(samples, "GET", "/admin/questionnaires/new") == "aicrm_next.frontend_compat.legacy_routes"
    assert _owner_for(samples, "GET", "/admin/questionnaires/21") == "next"
    assert _endpoint_for(samples, "GET", "/admin/questionnaires/21") == "aicrm_next.frontend_compat.legacy_routes"
    assert _owner_for(samples, "GET", "/api/admin/questionnaires/21") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/questionnaires/21") == "aicrm_next.questionnaire.api"
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
    assert _owner_for(samples, "GET", "/api/sidebar/lead-pool/status") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/lead-pool/status") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/sidebar/signup-tags/status") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/signup-tags/status") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/sidebar/marketing-status") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/marketing-status") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/sidebar/v2/workbench") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/v2/workbench") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/sidebar/v2/materials") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/v2/materials") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "POST", "/api/sidebar/bind-mobile") == "next"
    assert _endpoint_for(samples, "POST", "/api/sidebar/bind-mobile") == "aicrm_next.sidebar_write.api"
    assert _owner_for(samples, "POST", "/api/sidebar/v2/materials/send") == "next"
    assert _endpoint_for(samples, "POST", "/api/sidebar/v2/materials/send") == "aicrm_next.sidebar_write.api"
    assert _owner_for(samples, "GET", "/api/customers/automation/signup-conversion/batches") == "next"
    assert (
        _endpoint_for(samples, "GET", "/api/customers/automation/signup-conversion/batches")
        == "aicrm_next.automation_engine.api"
    )
    assert _owner_for(samples, "GET", "/api/customers/automation/signup-conversion/batches/1") == "next"
    assert _endpoint_for(samples, "GET", "/api/customers/automation/signup-conversion/batches/1") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "GET", "/api/customers/automation/webhook-deliveries") == "next"
    assert _endpoint_for(samples, "GET", "/api/customers/automation/webhook-deliveries") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "GET", "/api/admin/automation-conversion/agents/options") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/automation-conversion/agents/options") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "GET", "/api/admin/wecom/tags") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wecom/tags") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "POST", "/api/admin/wecom/tags") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wecom/tags") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "PATCH", "/api/admin/wecom/tags/tag_fixture_active") == "next"
    assert _endpoint_for(samples, "PATCH", "/api/admin/wecom/tags/tag_fixture_active") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "DELETE", "/api/admin/wecom/tags/tag_fixture_active") == "next"
    assert _endpoint_for(samples, "DELETE", "/api/admin/wecom/tags/tag_fixture_active") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "POST", "/api/admin/wecom/tags/sync") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wecom/tags/sync") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "POST", "/api/admin/wecom/tags/sync-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wecom/tags/sync-due") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "GET", "/api/admin/wecom/tag-groups") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wecom/tag-groups") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "POST", "/api/admin/wecom/tag-groups") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wecom/tag-groups") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "PATCH", "/api/admin/wecom/tag-groups/group_fixture_lifecycle") == "next"
    assert _endpoint_for(samples, "PATCH", "/api/admin/wecom/tag-groups/group_fixture_lifecycle") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "DELETE", "/api/admin/wecom/tag-groups/group_fixture_lifecycle") == "next"
    assert _endpoint_for(samples, "DELETE", "/api/admin/wecom/tag-groups/group_fixture_lifecycle") == "aicrm_next.customer_tags.api"


def test_high_risk_legacy_facade_routes_remain_production_compat_owned():
    result = checker.run_check()
    samples = result["resolution_samples"]

    assert _owner_for(samples, "POST", "/wecom/external-contact/callback") == "next"
    assert _endpoint_for(samples, "POST", "/wecom/external-contact/callback") == "aicrm_next.channel_entry.api"
    assert _owner_for(samples, "POST", "/api/wecom/events") == "next"
    assert _endpoint_for(samples, "POST", "/api/wecom/events") == "aicrm_next.channel_entry.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due") == "production_compat"
    assert _endpoint_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/batch-start") == "production_compat"
    assert _endpoint_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/batch-start") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "production_compat"
    assert _endpoint_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/admin/wechat-pay/products") == "next"
    assert _endpoint_for(samples, "GET", "/admin/wechat-pay/products") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/admin/wechat-pay/products/new") == "next"
    assert _endpoint_for(samples, "GET", "/admin/wechat-pay/products/new") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "POST", "/api/admin/wechat-pay/products") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wechat-pay/products") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products/lead-channels") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products/lead-channels") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products/1") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products/1") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products/1/share") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products/1/share") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "POST", "/api/admin/wechat-pay/products/1/copy") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wechat-pay/products/1/copy") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products/1/external-push") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products/1/external-push") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "PUT", "/api/admin/wechat-pay/products/1/external-push") == "next"
    assert _endpoint_for(samples, "PUT", "/api/admin/wechat-pay/products/1/external-push") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "POST", "/api/admin/wechat-pay/products/1/external-push/test") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wechat-pay/products/1/external-push/test") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/p/prd_20260518095708_9f77db") == "production_compat"
    assert _endpoint_for(samples, "GET", "/p/prd_20260518095708_9f77db") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/pay/prd_20260518095708_9f77db") == "production_compat"
    assert _endpoint_for(samples, "GET", "/pay/prd_20260518095708_9f77db") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/api/products/prd_20260518095708_9f77db") == "production_compat"
    assert _endpoint_for(samples, "GET", "/api/products/prd_20260518095708_9f77db") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/api/h5/wechat-pay/legacy-probe") == "production_compat"
    assert _endpoint_for(samples, "GET", "/api/h5/wechat-pay/legacy-probe") == "aicrm_next.production_compat.api"
    assert _owner_for(samples, "GET", "/api/sidebar/jssdk-config") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/jssdk-config") == "aicrm_next.identity_contact.sidebar_jssdk"
    assert _owner_for(samples, "POST", "/api/customers/automation/webhook-deliveries/1/retry") == "production_compat"
    assert (
        _endpoint_for(samples, "POST", "/api/customers/automation/webhook-deliveries/1/retry")
        == "aicrm_next.production_compat.api"
    )


def test_checker_reports_no_unexpected_shadowed_exact_routes_or_blockers():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["blockers"] == []
    unexpected_shadowed = [
        item
        for item in result["shadowed_exact_routes"]
        if item["manifest_route_pattern"]
            not in {
                "/api/admin/wecom/tags*",
                "/api/admin/wecom/tag-groups*",
                "/api/h5/questionnaires/{slug}/submit",
                "/api/h5/wechat/oauth*",
                "/p/{page_slug}",
                "/pay/{product_code}",
                "/api/products*",
        }
        and item["path"]
            not in {
                "/admin/hxc-dashboard",
                "/admin/hxc-send-config",
            }
    ]
    assert unexpected_shadowed == []
