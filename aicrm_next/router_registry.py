from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, FastAPI

from .ai_assist.api import router as ai_assist_router
from .ai_audience_ops.api import router as ai_audience_ops_router
from .admin_auth.api import router as admin_auth_router
from .admin_config.api import router as admin_config_router
from .admin_jobs.routes import router as admin_jobs_router
from .admin_shell.routes import router as admin_shell_router
from .automation_engine.admin_pages import router as automation_admin_pages_router
from .automation_engine.api import router as automation_router
from .automation_engine.channel_admin_pages import router as channel_admin_pages_router
from .automation_engine.channels_api import router as automation_channels_router
from .automation_engine.group_ops.admin_pages import router as group_ops_admin_pages_router
from .automation_runtime_v2.api import router as automation_runtime_v2_router
from .auth_wecom.api import router as auth_wecom_router
from .channel_entry.api import router as channel_entry_router
from .class_user_management.api import router as class_user_management_router
from .cloud_orchestrator.api import router as cloud_orchestrator_router
from .commerce.api import router as commerce_router
from .common_operation_members import router as common_operation_members_router
from .customer_read_model.admin_pages import router as customer_admin_pages_router
from .customer_read_model.api import router as customer_router
from .customer_tags.admin_pages import router as customer_tags_admin_pages_router
from .customer_tags.api import read_router as customer_tags_read_router
from .customer_tags.api import router as customer_tags_router
from .customer_tags.api import write_router as customer_tags_write_router
from .hxc_dashboard.api import router as hxc_dashboard_router
from .identity_contact.admin_pages import router as identity_admin_pages_router
from .identity_contact.api import router as identity_router
from .identity_contact.sidebar_jssdk import router as sidebar_jssdk_router
from .integration_gateway.api import router as mcp_router
from .media_library.admin_pages import router as media_library_admin_pages_router
from .media_library.api import router as media_library_router
from .message_archive.api import router as message_archive_router
from .ops_enrollment.admin_pages import router as user_ops_admin_pages_router
from .ops_enrollment.api import router as user_ops_router
from .owner_migration.api import router as owner_migration_router
from .platform_foundation.api import router as platform_router
from .platform_foundation.external_effects.api import router as external_effects_router
from .platform_foundation.internal_events.api import router as internal_events_router
from .platform_foundation.legacy_cleanup.api import router as legacy_cleanup_router
from .platform_foundation.push_center.api import router as push_center_router
from .public_product.api import router as public_product_router
from .questionnaire.admin_pages import router as questionnaire_admin_pages_router
from .questionnaire.api import router as questionnaire_router
from .radar_links.admin_pages import router as radar_links_admin_pages_router
from .radar_links.api import router as radar_links_router
from .send_content.api import router as send_content_router
from .sidebar_write.api import router as sidebar_write_router


@dataclass(frozen=True)
class RouterSpec:
    capability_owner: str
    route_group: str
    router: APIRouter
    notes: str = ""


ROUTER_SPECS: tuple[RouterSpec, ...] = (
    RouterSpec("platform_foundation", "platform", platform_router, "foundation health and shell contracts"),
    RouterSpec("platform_foundation", "external_effects", external_effects_router, "external effects job/admin APIs"),
    RouterSpec("platform_foundation", "legacy_cleanup", legacy_cleanup_router, "legacy cleanup read/command APIs"),
    RouterSpec("platform_foundation", "internal_events", internal_events_router, "internal event center APIs"),
    RouterSpec("platform_foundation", "push_center", push_center_router, "push center APIs"),
    RouterSpec("admin_auth", "admin_auth", admin_auth_router, "admin auth APIs"),
    RouterSpec("admin_shell", "admin_shell", admin_shell_router, "admin shell pages"),
    RouterSpec("admin_config", "admin_config", admin_config_router, "admin config pages and APIs"),
    RouterSpec("class_user_management", "class_user_management", class_user_management_router),
    RouterSpec("platform_foundation", "common_operation_members", common_operation_members_router),
    RouterSpec("channel_entry", "channel_entry", channel_entry_router),
    RouterSpec("automation_engine", "automation_channels", automation_channels_router),
    RouterSpec("hxc_dashboard", "hxc_dashboard", hxc_dashboard_router),
    RouterSpec("public_product", "public_product", public_product_router),
    RouterSpec("sidebar_write", "sidebar_write", sidebar_write_router),
    RouterSpec("identity_contact", "sidebar_jssdk", sidebar_jssdk_router),
    RouterSpec("customer_tags", "customer_tags_read", customer_tags_read_router),
    RouterSpec("customer_tags", "customer_tags_write", customer_tags_write_router),
    RouterSpec("cloud_orchestrator", "cloud_orchestrator", cloud_orchestrator_router),
    RouterSpec("customer_read_model", "customer_read_model", customer_router),
    RouterSpec("customer_read_model", "customer_admin_pages", customer_admin_pages_router),
    RouterSpec("customer_tags", "customer_tags", customer_tags_router),
    RouterSpec("ops_enrollment", "user_ops", user_ops_router),
    RouterSpec("ops_enrollment", "user_ops_admin_pages", user_ops_admin_pages_router),
    RouterSpec("integration_gateway", "mcp", mcp_router),
    RouterSpec("identity_contact", "identity", identity_router),
    RouterSpec("identity_contact", "identity_admin_pages", identity_admin_pages_router),
    RouterSpec("message_archive", "message_archive", message_archive_router),
    RouterSpec("questionnaire", "questionnaire_admin_pages", questionnaire_admin_pages_router),
    RouterSpec("questionnaire", "questionnaire", questionnaire_router),
    RouterSpec("radar_links", "radar_links_admin_pages", radar_links_admin_pages_router),
    RouterSpec("radar_links", "radar_links", radar_links_router),
    RouterSpec("auth_wecom", "auth_wecom", auth_wecom_router),
    RouterSpec("automation_engine", "group_ops_admin_pages", group_ops_admin_pages_router),
    RouterSpec("automation_engine", "automation_admin_pages", automation_admin_pages_router),
    RouterSpec("automation_engine", "channel_admin_pages", channel_admin_pages_router),
    RouterSpec("customer_tags", "customer_tags_admin_pages", customer_tags_admin_pages_router),
    RouterSpec("automation_engine", "automation", automation_router),
    RouterSpec("automation_runtime_v2", "automation_runtime_v2", automation_runtime_v2_router),
    RouterSpec("commerce", "commerce", commerce_router),
    RouterSpec("media_library", "media_library", media_library_router),
    RouterSpec("media_library", "media_library_admin_pages", media_library_admin_pages_router),
    RouterSpec("ai_assist", "ai_assist", ai_assist_router),
    RouterSpec("ai_audience_ops", "ai_audience_ops", ai_audience_ops_router, "AI audience package SQL refresh APIs"),
    RouterSpec("send_content", "send_content", send_content_router),
    RouterSpec("admin_jobs", "admin_jobs", admin_jobs_router),
    RouterSpec("owner_migration", "owner_migration", owner_migration_router),
)


def register_routers(app: FastAPI, specs: tuple[RouterSpec, ...] = ROUTER_SPECS) -> None:
    for spec in specs:
        app.include_router(spec.router)


def router_registry_summary(specs: tuple[RouterSpec, ...] = ROUTER_SPECS) -> list[dict[str, Any]]:
    return [
        {
            "capability_owner": spec.capability_owner,
            "route_group": spec.route_group,
            "route_count": len(getattr(spec.router, "routes", ()) or ()),
            "notes": spec.notes,
        }
        for spec in specs
    ]
