from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai_assist.api import router as ai_assist_router
from .automation_engine.api import router as automation_router
from .automation_engine.channels_api import router as automation_channels_router
from .automation_engine.group_ops.repo import reset_group_ops_fixture_state
from .automation_engine.repo import reset_automation_fixture_state
from .commerce.api import router as commerce_router
from .commerce.repo import reset_commerce_fixture_state
from .customer_tags.api import router as customer_tags_router
from .customer_read_model.api import router as customer_router
from .frontend_compat.legacy_routes import router as frontend_compat_router
from .identity_contact.api import router as identity_router
from .integration_gateway.api import router as mcp_router
from .media_library.api import router as media_library_router
from .media_library.repo import reset_media_library_fixture_state
from .ops_enrollment.application import reset_user_ops_fixture_state
from .ops_enrollment.api import router as user_ops_router
from .platform_foundation.api import router as platform_router
from .production_compat.api import router as production_compat_router
from .production_compat.api import wildcard_router as production_compat_wildcard_router
from .questionnaire.api import router as questionnaire_router
from .send_content.api import router as send_content_router
from .shared.repository_provider import RepositoryProviderError
from .shared.runtime import legacy_production_facade_enabled
from .shared.runtime import fixture_mode
from .questionnaire.repo import reset_questionnaire_fixture_state

_FRONTEND_COMPAT_DIR = Path(__file__).resolve().parent / "frontend_compat"


def create_app() -> FastAPI:
    app = FastAPI(title="AI-CRM Next", version="0.1.0")

    if fixture_mode():
        reset_user_ops_fixture_state()
        reset_questionnaire_fixture_state()
        reset_automation_fixture_state()
        reset_group_ops_fixture_state()
        reset_commerce_fixture_state()
        reset_media_library_fixture_state()

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
        "/static",
        StaticFiles(directory=_FRONTEND_COMPAT_DIR / "static"),
        name="static",
    )
    app.include_router(platform_router)
    app.include_router(automation_channels_router)
    if legacy_production_facade_enabled():
        app.include_router(production_compat_router)
    app.include_router(customer_router)
    app.include_router(customer_tags_router)
    app.include_router(user_ops_router)
    app.include_router(mcp_router)
    app.include_router(identity_router)
    app.include_router(questionnaire_router)
    app.include_router(automation_router)
    app.include_router(commerce_router)
    app.include_router(media_library_router)
    app.include_router(ai_assist_router)
    app.include_router(send_content_router)
    app.include_router(frontend_compat_router)
    if legacy_production_facade_enabled():
        app.include_router(production_compat_wildcard_router)
    return app


app = create_app()
