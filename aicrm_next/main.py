from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .admin_auth import reset_admin_auth_fixture_state
from .admin_jobs.repository import reset_admin_jobs_fixture_state
from .automation_engine.group_ops.repo import reset_group_ops_fixture_state
from .automation_engine.customer_webhooks import reset_customer_webhook_fixture_state
from .automation_engine.member_actions import reset_member_actions_fixture_state
from .automation_engine.repo import reset_automation_fixture_state
from .automation_engine.channels_api import reset_wecom_customer_acquisition_link_fixture_state
from .commerce.repo import reset_commerce_fixture_state
from .cloud_orchestrator.campaigns_read import reset_campaign_read_fixture_state
from .cloud_orchestrator.campaigns_write import reset_campaign_write_fixture_state
from .cloud_orchestrator.repository import reset_cloud_plan_fixture_state
from .customer_tags.admin_write import reset_wecom_tag_write_fixture_state
from .customer_tags.live_mutation import reset_wecom_tag_live_mutation_fixture_state
from .hxc_dashboard.repo import reset_hxc_dashboard_fixture_state
from .hxc_dashboard.safe_mode import reset_hxc_safe_mode_fixture_state
from .integration_gateway.wecom_jssdk_adapter import reset_sidebar_jssdk_attempts
from .media_library.repo import reset_media_library_fixture_state
from .ops_enrollment.application import reset_user_ops_fixture_state
from .platform_foundation.external_effects import reset_external_effect_fixture_state
from .platform_foundation.legacy_cleanup import reset_legacy_cleanup_fixture_state
from .platform_foundation.internal_events import register_payment_succeeded_consumers, register_shadow_event_consumers, reset_internal_event_fixture_state
from .radar_links.repo import reset_radar_links_fixture_state
from .sidebar_write import reset_sidebar_write_fixture_state
from .router_registry import register_routers
from .shared.repository_provider import RepositoryProviderError
from .shared.runtime import fixture_mode
from .questionnaire.repo import reset_questionnaire_fixture_state
from .questionnaire.admin_write import reset_questionnaire_admin_write_fixture_state
from .questionnaire.h5_write import reset_questionnaire_h5_write_fixture_state

_FRONTEND_COMPAT_DIR = Path(__file__).resolve().parent / "frontend_compat"
_GROUP_OPS_DIR = Path(__file__).resolve().parent / "automation_engine" / "group_ops"
_AUTOMATION_ENGINE_DIR = Path(__file__).resolve().parent / "automation_engine"
_CUSTOMER_TAGS_DIR = Path(__file__).resolve().parent / "customer_tags"


def create_app() -> FastAPI:
    app = FastAPI(title="AI-CRM Next", version="0.1.0")
    register_payment_succeeded_consumers()
    register_shadow_event_consumers()

    if fixture_mode():
        reset_user_ops_fixture_state()
        reset_questionnaire_fixture_state()
        reset_questionnaire_h5_write_fixture_state()
        reset_automation_fixture_state()
        reset_customer_webhook_fixture_state()
        reset_member_actions_fixture_state()
        reset_group_ops_fixture_state()
        reset_commerce_fixture_state()
        reset_media_library_fixture_state()
        reset_admin_jobs_fixture_state()
        reset_hxc_dashboard_fixture_state()
        reset_hxc_safe_mode_fixture_state()
        reset_radar_links_fixture_state()
        reset_cloud_plan_fixture_state()
        reset_campaign_read_fixture_state()
        reset_campaign_write_fixture_state()
        reset_sidebar_write_fixture_state()
        reset_wecom_customer_acquisition_link_fixture_state()
        reset_admin_auth_fixture_state()
        reset_questionnaire_admin_write_fixture_state()
        reset_wecom_tag_write_fixture_state()
        reset_wecom_tag_live_mutation_fixture_state()
        reset_sidebar_jssdk_attempts()
        reset_external_effect_fixture_state()
        reset_legacy_cleanup_fixture_state()
        reset_internal_event_fixture_state()

    @app.exception_handler(RepositoryProviderError)
    async def repository_provider_error_handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "degraded": True,
                "source_status": "production_unavailable",
                "error_code": "fixture_repository_blocked_in_production",
                "detail": str(exc),
            },
        )

    @app.middleware("http")
    async def write_route_owner_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-AICRM-Route-Owner", "ai_crm_next")
        response.headers.setdefault("X-AICRM-App", "ai_crm_next")
        response.headers.setdefault("X-AICRM-Release-SHA", os.getenv("AICRM_NEXT_RELEASE_SHA") or os.getenv("RELEASE_SHA") or "unknown")
        return response

    app.mount(
        "/static/group-ops",
        StaticFiles(directory=_GROUP_OPS_DIR / "static"),
        name="group_ops_static",
    )
    app.mount(
        "/static/automation-engine",
        StaticFiles(directory=_AUTOMATION_ENGINE_DIR / "static"),
        name="automation_engine_static",
    )
    app.mount(
        "/static/customer-tags",
        StaticFiles(directory=_CUSTOMER_TAGS_DIR / "static"),
        name="customer_tags_static",
    )
    app.mount(
        "/static",
        StaticFiles(directory=_FRONTEND_COMPAT_DIR / "static"),
        name="static",
    )
    register_routers(app)
    return app


app = create_app()
