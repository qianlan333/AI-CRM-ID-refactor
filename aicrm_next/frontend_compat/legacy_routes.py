from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)
_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

LEGACY_FRONTEND_ROUTES = []


@router.get("/sidebar/bind-mobile", name="api.sidebar_bind_mobile_page")
async def sidebar_bind_mobile_page(request: Request):
    return templates.TemplateResponse(
        request,
        "sidebar_customer_workbench.html",
        {"request": request, "debug_enabled": False},
    )


@router.get("/api/frontend-compat/legacy-routes")
def legacy_routes_manifest() -> dict:
    return {
        "ok": True,
        "frontend_parity_policy": "1:1 replicate existing AI-CRM admin frontend; do not redesign",
        "routes": LEGACY_FRONTEND_ROUTES,
    }
