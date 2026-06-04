from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from aicrm_next.shared.errors import NotFoundError

from .service import (
    blocked_action_payload,
    diagnostics_payload,
    get_public_product,
    list_public_products,
    normalize_public_path,
    payment_action_detected,
    product_not_found_payload,
    public_product_payload,
    render_not_found_page,
    render_pay_landing,
    render_product_page,
    route_headers,
)


router = APIRouter()


@router.options("/p/{path:path}", name="api.public_product_page_options")
def public_product_page_options(path: str) -> JSONResponse:
    return JSONResponse(diagnostics_payload(f"/p/{path}", allowed_methods=["GET", "HEAD", "OPTIONS"]), headers=route_headers())


@router.api_route("/p/{path:path}", methods=["GET", "HEAD"], response_class=HTMLResponse, name="api.public_product_page")
def public_product_page(request: Request, path: str) -> Response:
    try:
        product = get_public_product(path)
    except NotFoundError:
        return HTMLResponse(render_not_found_page(path), status_code=404, headers=route_headers())
    return HTMLResponse(render_product_page(product), headers=route_headers())


@router.options("/pay/{path:path}", name="api.public_pay_landing_options")
def public_pay_landing_options(path: str) -> JSONResponse:
    return JSONResponse(diagnostics_payload(f"/pay/{path}", allowed_methods=["GET", "HEAD", "OPTIONS"]), headers=route_headers())


@router.api_route("/pay/{path:path}", methods=["GET", "HEAD"], response_class=HTMLResponse, name="api.public_pay_landing")
def public_pay_landing(request: Request, path: str) -> Response:
    try:
        product = get_public_product(path)
    except NotFoundError:
        return HTMLResponse(render_not_found_page(path), status_code=404, headers=route_headers())
    return HTMLResponse(render_pay_landing(product), headers=route_headers())


@router.options("/api/products/{path:path}", name="api.public_product_api_options")
def public_product_api_options(path: str) -> JSONResponse:
    return JSONResponse(diagnostics_payload(f"/api/products/{path}", allowed_methods=["GET", "HEAD", "OPTIONS"]), headers=route_headers())


@router.api_route("/api/products/{path:path}", methods=["GET", "HEAD"], name="api.public_product_api")
def public_product_api(path: str) -> JSONResponse:
    try:
        normalized = normalize_public_path(path)
        if normalized == "list":
            return JSONResponse(list_public_products(), headers=route_headers())
        if payment_action_detected(normalized):
            return JSONResponse(blocked_action_payload(normalized, method="GET"), status_code=410, headers=route_headers())
        return JSONResponse(public_product_payload(normalized), headers=route_headers())
    except NotFoundError:
        return JSONResponse(product_not_found_payload(path), status_code=404, headers=route_headers())


@router.api_route("/api/products/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE"], name="api.public_product_api_blocked_write")
async def public_product_api_blocked_write(request: Request, path: str) -> JSONResponse:
    return JSONResponse(blocked_action_payload(path, method=request.method), status_code=410, headers=route_headers())
