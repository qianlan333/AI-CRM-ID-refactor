from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from aicrm_next.shared.release import current_release_sha

from .api import callback_router


def create_wecom_callback_ingress_app() -> FastAPI:
    app = FastAPI(title="AI-CRM WeCom Callback Ingress", version="0.1.0")

    @app.middleware("http")
    async def write_ingress_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-AICRM-Route-Owner", "ai_crm_next")
        response.headers.setdefault("X-AICRM-Fallback-Used", "false")
        response.headers.setdefault("X-AICRM-App", "ai_crm_wecom_ingress")
        response.headers.setdefault("X-AICRM-Release-SHA", current_release_sha())
        return response

    @app.get("/health", name="wecom_callback_ingress_health")
    def health() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "runtime": "ai_crm_wecom_ingress",
                "route_owner": "ai_crm_next",
                "release_sha": current_release_sha(),
            }
        )

    app.include_router(callback_router)
    return app


app = create_wecom_callback_ingress_app()
